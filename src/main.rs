use std::collections::HashMap;
use std::fs::File;
use std::io::{BufReader, Read, Seek, SeekFrom};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex};

use clap::Parser;
use memmap2::MmapOptions;

#[derive(Clone, Copy)]
enum Job {
    Tokenize((usize, usize)),
}

#[derive(Clone)]
struct Stats {
    byte_count: [usize; 256],
}

impl Stats {
    fn new() -> Self {
        Stats {
            byte_count: [0; 256],
        }
    }

    fn process_byte(&mut self, byte: u8) {
        self.byte_count[byte as usize] += 1;
    }
}

#[derive(Clone, Debug)]
struct Token {
    string: Vec<u8>,
    is_literal: bool,
    // Index of the longest other token which is a suffix of this one.
    suffix: Option<usize>,
}

impl Token {
    fn new(string: &[u8], is_literal: bool) -> Self {
        Token {
            string: string.to_vec(),
            is_literal,
            suffix: None,
        }
    }
}

#[derive(Clone)]
struct TokenSet {
    tokens: Vec<Token>,
    tokens_by_string: HashMap<Vec<u8>, usize>,
    literal_cost: usize,
    ntokens: usize,
}

impl TokenSet {
    fn add_token(&mut self, string: &[u8], is_literal: bool) {
        if let Some(&existing) = self.tokens_by_string.get(string) {
            let existing = &self.tokens[existing];
            if !existing.is_literal {
                return
            }
        }

        let index = self.tokens.len();
        let token = Token::new(string, is_literal);
        self.tokens_by_string.insert(token.string.clone(), index);
        self.tokens.push(token);
        self.ntokens += 1;
    }

    fn build_with_hex_literals() -> Self {
        let mut token_set = TokenSet {
            tokens: Vec::new(),
            tokens_by_string: HashMap::new(),
            literal_cost: 3,
            ntokens: 0,
        };

        for i in 0..=255 {
            token_set.add_token(&[i], true);
        }
        token_set.add_token(&[0x10], false);
        for i in ('0' as u8)..=('9' as u8) {
            token_set.add_token(&[i], false);
        }
        for i in ('a' as u8)..=('f' as u8) {
            token_set.add_token(&[i], false);
        }

        token_set.ntokens = token_set.tokens.len();

        token_set
    }

    fn build_with_bin_literals() -> Self {
        let mut token_set = TokenSet {
            tokens: Vec::new(),
            tokens_by_string: HashMap::new(),
            literal_cost: 8,
            ntokens: 0,
        };

        for i in 0..=255 {
            token_set.add_token(&[i], true);
        }
        token_set.add_token(&[0x11], false);
        token_set.add_token(&[0x12], false);

        token_set.ntokens = token_set.tokens.len();

        token_set
    }

    fn generate_suffixes(&mut self) {
        for i in 256..self.tokens.len() {
            let mut token = &mut self.tokens[i];
            for start in 1..token.string.len() {
                if let Some(&idx) = self.tokens_by_string.get(&token.string[start..]) {
                    token.suffix = Some(idx);
                    break;
                }
            }
        }
    }

    fn to_json(&self) -> json::JsonValue {
        let mut out = json::object! {
            tokens: []
        };

        for token in self.tokens.iter() {
            if token.is_literal {
                continue;
            }

            let value: json::JsonValue = match std::str::from_utf8(&token.string) {
                Ok(s) => s.into(),
                Err(_) => token.string.as_slice().into(),
            };

            out["tokens"].push(value).unwrap();
        }

        out
    }
}

#[derive(Debug)]
struct SuffixState {
    suffix: Vec<u8>,
    token_id: usize,
    next: [usize; 256],
}

impl SuffixState {
    fn new(suffix: Vec<u8>, token_id: usize) -> Self {
        SuffixState {
            suffix,
            token_id,
            next: [0; 256],
        }
    }
}

struct DynState {
    cost: usize,
    token_id: usize,
}

struct TokenStats {
    token_count: Vec<usize>,
    pair_count: Vec<usize>,
    cost: usize,
    scanned_bytes: usize,
}

impl TokenStats {
    fn new(token_set: &TokenSet) -> Self {
        let n = token_set.tokens.len();

        let mut token_count = Vec::with_capacity(n);
        token_count.resize(n, 0);

        let mut pair_count = Vec::with_capacity(n * n);
        pair_count.resize(n * n, 0);

        TokenStats {
            token_count,
            pair_count,
            cost: 0,
            scanned_bytes: 0,
        }
    }

    fn add(&mut self, other: &TokenStats) {
        for i in 0..self.token_count.len() {
            self.token_count[i] += other.token_count[i];
        }
        for i in 0..self.pair_count.len() {
            self.pair_count[i] += other.pair_count[i];
        }
        self.cost += other.cost;
        self.scanned_bytes += other.scanned_bytes;
    }
}

struct Tokenizer {
    token_set: TokenSet,
    suffix_states: Vec<SuffixState>,
    current_state: usize,
    cost_array: Vec<DynState>,
}

impl Tokenizer {
    fn new(mut token_set: TokenSet) -> Self {
        token_set.generate_suffixes();
        let suffix_states = Self::create_suffix_states(&token_set);

        Tokenizer {
            token_set,
            suffix_states,
            current_state: 0,
            cost_array: vec![DynState {
                cost: 0,
                token_id: 0x13,
            }],
        }
    }

    fn create_suffix_states(token_set: &TokenSet) -> Vec<SuffixState> {
        let mut suffix_states = Vec::new();
        let mut state_by_str: HashMap<Vec<u8>, usize> = HashMap::new();

        suffix_states.push(SuffixState::new(Vec::new(), 0));

        state_by_str.insert(Vec::new(), 0);

        for token in token_set.tokens.iter() {
            for end in 1..=token.string.len() {
                // The suffix is a token prefix
                let suffix = token.string[..end].to_vec();

                if state_by_str.contains_key(&suffix) {
                    continue;
                }

                let mut suffix_token = None;
                for token_start in 0..suffix.len() {
                    if let Some(&idx) = token_set.tokens_by_string.get(&suffix[token_start..]) {
                        suffix_token = Some(idx);
                        break;
                    }
                }

                assert!(suffix_token.is_some());

                let suffix_state = SuffixState::new(suffix, suffix_token.unwrap());

                let state_idx = suffix_states.len();
                state_by_str.insert(suffix_state.suffix.to_vec(), state_idx);
                suffix_states.push(suffix_state);
            }
        }

        for mut state in suffix_states.iter_mut() {
            let mut suffix = state.suffix.to_vec();

            for last_byte in 0..=255 {
                suffix.push(last_byte);

                let mut suffix_id: Option<usize> = None;

                for start in 0..suffix.len() {
                    let suffix_suffix = &suffix[start..];

                    if let Some(&id) = state_by_str.get(suffix_suffix) {
                        suffix_id = Some(id);
                        break;
                    }
                }

                state.next[last_byte as usize] = suffix_id.unwrap();

                suffix.pop();
            }
        }

        suffix_states
    }

    fn reset(&mut self) {
        self.current_state = 0;
        self.cost_array.clear();
        self.cost_array.push(DynState {
            cost: 0,
            token_id: 0x13,
        });
    }

    fn process_byte(&mut self, byte: u8) {
        // dbg!(byte);
        let prev_state = &self.suffix_states[self.current_state];
        self.current_state = prev_state.next[byte as usize];
        let state = &self.suffix_states[self.current_state];
        // dbg!(state);

        let mut best_dyn_state = DynState {
            cost: std::usize::MAX,
            token_id: 0,
        };

        let mut token_id = state.token_id;
        loop {
            let token = &self.token_set.tokens[token_id];
            let prev_cost = self.cost_array[self.cost_array.len() - token.string.len()].cost;
            let new_cost = prev_cost
                + if token.is_literal {
                    self.token_set.literal_cost
                } else {
                    1
                };

            if new_cost < best_dyn_state.cost {
                best_dyn_state.cost = new_cost;
                best_dyn_state.token_id = token_id;
            }

            if let Some(t) = token.suffix {
                token_id = t;
            } else {
                break;
            }
        }

        self.cost_array.push(best_dyn_state);
    }

    fn process_slice(&mut self, bytes: &[u8]) {
        let mut state = &self.suffix_states[self.current_state];

        for &byte in bytes.iter() {
            self.current_state = state.next[byte as usize];
            state = &self.suffix_states[self.current_state];

            let mut best_dyn_state = DynState {
                cost: std::usize::MAX,
                token_id: 0,
            };

            let mut token_id = state.token_id;
            loop {
                let token = &self.token_set.tokens[token_id];
                let prev_cost = self.cost_array[self.cost_array.len() - token.string.len()].cost;
                let new_cost = prev_cost
                    + if token.is_literal {
                        self.token_set.literal_cost
                    } else {
                        1
                    };

                if new_cost < best_dyn_state.cost {
                    best_dyn_state.cost = new_cost;
                    best_dyn_state.token_id = token_id;
                }

                if let Some(t) = token.suffix {
                    token_id = t;
                } else {
                    break;
                }
            }

            self.cost_array.push(best_dyn_state);
        }
    }

    fn get_stats(&self) -> TokenStats {
        let mut token_stats = TokenStats::new(&self.token_set);

        let mut pos = self.cost_array.len() - 1;
        token_stats.cost = self.cost_array[pos].cost;
        token_stats.scanned_bytes = pos;

        let mut next_token_id = 0;

        while pos > 0 {
            let token_id = self.cost_array[pos].token_id;
            let token = &self.token_set.tokens[token_id];
            token_stats.token_count[token_id] += 1;

            token_stats.pair_count[token_id * self.token_set.ntokens + next_token_id] += 1;

            next_token_id = token_id;
            pos = pos.checked_sub(token.string.len()).unwrap();
        }

        token_stats
    }
}

const CHUNK_SIZE: usize = 32 * 1024 * 1024;
const BUFFER_SIZE: usize = 256 * 1024;

fn worker(
    token_set: TokenSet,
    filename: &str,
    jobs_rx: Arc<Mutex<Receiver<Job>>>,
    results_tx: Sender<TokenStats>,
) {
    let mut tokenizer = Tokenizer::new(token_set);

    let mut file = File::open(filename).unwrap();

    let mut buffer = Vec::with_capacity(BUFFER_SIZE);
    buffer.resize(BUFFER_SIZE, 0);
    let mut max_read = 0;

    loop {
        tokenizer.reset();

        let (start, finish) = {
            match jobs_rx.lock().unwrap().recv() {
                Ok(Job::Tokenize((start, finish))) => (start, finish),
                Err(_) => break,
            }
        };

        if start == finish {
            break;
        }

        // let mut reader = BufReader::with_capacity(1024 * 1024, &file);
        // reader.seek(SeekFrom::Start(start as u64)).unwrap();

        // for byte in reader.take((finish - start) as u64).bytes() {
        //     tokenizer.process_byte(byte.unwrap());
        // }

        let mut to_read = finish - start;

        while to_read > 0 {
            let buf_to_read = std::cmp::min(to_read, BUFFER_SIZE);
            let buffer_to_read = &mut buffer[0..buf_to_read];
            let read_bytes = file.read(buffer_to_read).unwrap();
            if read_bytes == 0 {
                break;
            }
            to_read -= read_bytes;

            let buffer_read = &buffer_to_read[0..read_bytes];

            tokenizer.process_slice(buffer_read);
            // for &byte in buffer_read {
            //     tokenizer.process_byte(byte);
            // }
        }

        results_tx.send(tokenizer.get_stats()).unwrap();
    }
}

fn tokenize_file(token_set: &TokenSet, filename: &str, splits: &[usize]) -> TokenStats {
    let (jobs_tx, jobs_rx) = mpsc::channel::<Job>();
    let jobs_rx_shared = Arc::new(Mutex::new(jobs_rx));
    let (results_tx, results_rx) = mpsc::channel::<TokenStats>();

    let mut total_stats = TokenStats::new(token_set);

    std::thread::scope(|s| {
        let mut join_handles = Vec::new();

        for _ in 0..std::thread::available_parallelism().unwrap().get() {
            let jobs_rx_clone = jobs_rx_shared.clone();
            let results_tx_clone = results_tx.clone();
            join_handles.push(s.spawn(move || {
                worker(token_set.clone(), filename, jobs_rx_clone, results_tx_clone)
            }));
        }

        let start = std::time::Instant::now();
        let mut njobs = 0;
        for islice in 0..splits.len() - 1 {
            let start = splits[islice];
            let end = splits[islice + 1];
            jobs_tx.send(Job::Tokenize((start, end))).unwrap();
            njobs += 1;
        }

        std::mem::drop(jobs_tx);

        for i in 0..njobs {
            let stats = results_rx.recv().unwrap();
            total_stats.add(&stats);
            if splits[splits.len() - 1] > 100000000 {
                let elapsed = std::time::Instant::now() - start;
                eprint!(
                    "\rAvg pace: {:.1} MB / s",
                    total_stats.scanned_bytes as f64 / 1000000.0 / elapsed.as_secs_f64()
                );
            }
        }
        eprintln!();

        while !join_handles.is_empty() {
            join_handles.pop().unwrap().join().unwrap();
        }
    });

    total_stats
}

fn optimize_bpe(
    token_set: &TokenSet,
    ntokens: usize,
    filename: &str,
    splits: &[usize],
) -> TokenSet {
    let mut token_set = token_set.clone();
    while token_set.ntokens < 256 + ntokens {
            // loop {
        let stats = tokenize_file(&token_set, filename, splits);

        let mut top_literal = 0;
        let mut top_literal_count = 0;

        for i in 0..256 {
            if stats.token_count[i] > top_literal_count {
                top_literal = i;
                top_literal_count = stats.token_count[i];
            }
        }

        println!(
            "Top literal: {} with count {}",
            top_literal, top_literal_count
        );

        let mut top_pair = 0;
        let mut top_pair_count = 0;
        for ipair in 0..stats.pair_count.len() {
            if stats.pair_count[ipair] > top_pair_count {
                top_pair = ipair;
                top_pair_count = stats.pair_count[ipair];
            }
        }

        let ifirst = top_pair / token_set.ntokens;
        let isecond = top_pair % token_set.ntokens;

        let mut token_str = token_set.tokens[ifirst].string.clone();
        token_str.extend(token_set.tokens[isecond].string.clone());

        println!(
            "Top pair: {:?} with count {}", &token_str, top_pair_count
        );

        let new_token_str = if top_literal_count > top_pair_count {
            vec![top_literal as u8]
        } else {
            token_str
        };

        let mut new_token_set = token_set.clone();
        new_token_set.add_token(&new_token_str, false);

        match String::from_utf8(new_token_str.clone()) {
            Ok(string) => {
                println!("Adding token {:?}", string)
            }
            Err(_) => {
                println!("Adding token {:?}", &new_token_str)
            }
        }

        // if new_token_set.ntokens > 256 + ntokens {

        // }

        token_set = new_token_set;
    }

    token_set
}

fn split_into_chunks(filename: &str, chunk_size: usize) -> Vec<usize> {
    let file = File::open(filename).unwrap();
    let data = unsafe { MmapOptions::new().map(&file).unwrap() };

    let mut split = 0;
    let mut splits = vec![0];

    while split < data.len() {
        let end_bound = std::cmp::min(split + chunk_size, data.len());
        let delta = data[end_bound..].iter().position(|&b| b == 0x13);
        let end = match delta {
            Some(p) => end_bound + p + 1,
            None => data.len(),
        };

        splits.push(end);
        split = end;
    }

    let mut min_slice = 1 << 40;
    let mut max_slice = 0;

    for i in 0..splits.len() - 1 {
        let start = splits[i];
        let end = splits[i + 1];
        let len = end - start;
        if len > max_slice {
            max_slice = len;
        }
        if len < min_slice {
            min_slice = len;
        }
    }

    eprintln!(
        "Created {} splits, smallest {}, biggest {}",
        splits.len() - 1,
        min_slice,
        max_slice
    );

    splits
}

#[derive(Parser, Debug)]
struct Args {
    #[arg(short, long, default_value_t = String::new())]
    data: String,

    #[arg(short, long, default_value_t = String::new())]
    input: String,

    #[arg(short, long, default_value_t = String::new())]
    output: String,

    #[arg(short, long, default_value_t = 0)]
    ntokens: usize,
}

fn main() {
    let args = Args::parse();

    let mut token_set =
        if args.input.is_empty() {
            TokenSet::build_with_bin_literals()
        } else {
            let contents = std::fs::read_to_string(args.input).unwrap();
            let parsed = json::parse(&contents).unwrap();

            let mut token_set = if parsed["config"]["fallback16"].as_bool().unwrap() {
                TokenSet::build_with_hex_literals()
            } else {
                TokenSet::build_with_bin_literals()
            };

            for token_str in parsed["tokens"].members() {
                dbg!(token_str);
                if token_str.is_string() {
                    token_set.add_token(token_str.as_str().unwrap().as_bytes(), false);
                } else {
                    let mut s = vec![];
                    for b in token_str.members() {
                        s.push(b.as_u8().unwrap());
                    }
                    token_set.add_token(&s, false);
                }
            }

            token_set
        };


    let tokens_json = token_set.to_json();
    println!("{}", json::stringify(tokens_json));

    let filename = args.data.as_str();
    let splits = split_into_chunks(filename, CHUNK_SIZE);

    let token_set = optimize_bpe(&token_set, args.ntokens, filename, &splits);

    let tokens_json = token_set.to_json();
    let tokens_json_str = json::stringify(tokens_json);
    println!("{}", &tokens_json_str);

    let stats = tokenize_file(&token_set, filename, &splits);
    println!("Cost: {}", stats.cost);

    if !args.output.is_empty() {
        std::fs::write(args.output, &tokens_json_str).unwrap();
    }
}
