use std::collections::HashMap;
use std::fs::File;
use std::io::{BufReader, Read, Seek, SeekFrom};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex};

use clap::Parser;
use memmap2::MmapOptions;

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
    is_mandatory: bool,
    // Index of the longest other token which is a suffix of this one.
    suffix: Option<usize>,
    cost: usize,
}

impl Token {
    fn new(string: &[u8], is_literal: bool, is_mandatory: bool, cost: usize) -> Self {
        Token {
            string: string.to_vec(),
            is_literal,
            is_mandatory,
            suffix: None,
            cost,
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
    fn add_mandatory_token(&mut self, string: &[u8]) {
        if let Some(&existing) = self.tokens_by_string.get(string) {
            let existing = &self.tokens[existing];
            assert!(existing.is_literal);
        }
        let index = self.tokens.len();
        let token = Token::new(string, false, true, 1);
        self.tokens_by_string.insert(token.string.clone(), index);
        self.tokens.push(token);
        self.ntokens += 1;
    }

    fn add_token(&mut self, string: &[u8]) {
        if let Some(&existing) = self.tokens_by_string.get(string) {
            let existing = &self.tokens[existing];
            if !existing.is_literal {
                return;
            }
        }

        let index = self.tokens.len();
        let token = Token::new(string, false, false, 1);
        self.tokens_by_string.insert(token.string.clone(), index);
        self.tokens.push(token);
        self.ntokens += 1;
    }

    fn add_literal(&mut self, value: u8) {
        let token = Token::new(&[value], true, false, self.literal_cost);
        self.tokens_by_string
            .insert(token.string.clone(), self.tokens.len());
        self.tokens.push(token);
        self.ntokens += 1;
    }

    fn remove_token(&mut self, token_id: usize) {
        assert!(token_id >= 256); // Can't remove literals
        self.tokens.remove(token_id);
        self.ntokens -= 1;

        self.tokens_by_string.clear();
        for i in 0..self.ntokens {
            let token = &self.tokens[i];
            self.tokens_by_string.insert(token.string.clone(), i);
        }
    }

    fn build_with_hex_literals() -> Self {
        let mut token_set = TokenSet {
            tokens: Vec::new(),
            tokens_by_string: HashMap::new(),
            literal_cost: 3,
            ntokens: 0,
        };

        for i in 0..=255 {
            token_set.add_literal(i);
        }
        token_set.add_mandatory_token(&[0x10]);
        for i in ('0' as u8)..=('9' as u8) {
            token_set.add_mandatory_token(&[i]);
        }
        for i in ('a' as u8)..=('f' as u8) {
            token_set.add_mandatory_token(&[i]);
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
            token_set.add_literal(i);
        }
        token_set.add_mandatory_token(&[0x11]);
        token_set.add_mandatory_token(&[0x12]);

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

        let mut token_strs = vec![];

        for token in self.tokens.iter() {
            if !token.is_literal {
                token_strs.push(token.string.clone());
            }
        }

        token_strs.sort_unstable();

        for token_str in token_strs.iter() {
            let value: json::JsonValue = match std::str::from_utf8(&token_str) {
                Ok(s) => s.into(),
                Err(_) => token_str.as_slice().into(),
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
    // current_state: usize,
    cost_array: Vec<DynState>,
}

impl Tokenizer {
    fn new(mut token_set: TokenSet) -> Self {
        token_set.generate_suffixes();
        let suffix_states = Self::create_suffix_states(&token_set);

        Tokenizer {
            token_set,
            suffix_states,
            cost_array: Vec::new(),
            // current_state: 0,
            // cost_array: vec![DynState {
            //     cost: 0,
            //     token_id: 0x13,
            // }],
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

    fn process_slice(&mut self, bytes: &[u8]) -> TokenStats {
        self.cost_array.truncate(0);
        self.cost_array.push(DynState {
            cost: 0,
            token_id: 0x13,
        });

        let mut state = &self.suffix_states[0];

        for &byte in bytes.iter() {
            state = &self.suffix_states[state.next[byte as usize]];

            let mut best_dyn_state = DynState {
                cost: std::usize::MAX,
                token_id: 0,
            };

            let mut token_id = state.token_id;
            loop {
                let token = &self.token_set.tokens[token_id];
                let prev_cost = self.cost_array[self.cost_array.len() - token.string.len()].cost;
                let new_cost = prev_cost + token.cost;

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
        self.get_stats(&self.cost_array)
    }

    fn get_stats(&self, cost_array: &[DynState]) -> TokenStats {
        let mut token_stats = TokenStats::new(&self.token_set);

        let mut pos = cost_array.len() - 1;
        token_stats.cost = cost_array[pos].cost;
        token_stats.scanned_bytes = pos;

        let mut next_token_id = 0;

        while pos > 0 {
            let token_id = cost_array[pos].token_id;
            let token = &self.token_set.tokens[token_id];
            token_stats.token_count[token_id] += 1;

            token_stats.pair_count[token_id * self.token_set.ntokens + next_token_id] += 1;

            next_token_id = token_id;
            pos = pos.checked_sub(token.string.len()).unwrap();
        }

        token_stats
    }
}

const CHUNK_SIZE: usize = 16 * 1024 * 1024;

struct Job {
    data: Vec<u8>,
}

fn worker(token_set: TokenSet, jobs_rx: Arc<Mutex<Receiver<Job>>>, results_tx: Sender<TokenStats>) {
    let mut tokenizer = Tokenizer::new(token_set);

    loop {
        let data = {
            match jobs_rx.lock().unwrap().recv() {
                Ok(Job { data }) => data,
                Err(_) => break,
            }
        };

        assert!(!data.is_empty());

        results_tx.send(tokenizer.process_slice(&data)).unwrap();
    }
}

fn tokenize_file(token_set: &TokenSet, filename: &str) -> TokenStats {
    let nthreads = std::thread::available_parallelism().unwrap().get();

    let (jobs_tx, jobs_rx) = mpsc::sync_channel::<Job>(2);
    let jobs_rx_shared = Arc::new(Mutex::new(jobs_rx));
    let (results_tx, results_rx) = mpsc::channel::<TokenStats>();
    let mut file = File::open(filename).unwrap();

    let mut total_stats = TokenStats::new(token_set);

    std::thread::scope(|s| {
        let mut join_handles = Vec::new();

        for _ in 0..nthreads {
            let jobs_rx_clone = jobs_rx_shared.clone();
            let results_tx_clone = results_tx.clone();
            join_handles
                .push(s.spawn(move || worker(token_set.clone(), jobs_rx_clone, results_tx_clone)));
        }

        let start = std::time::Instant::now();
        let mut jobs_in_flight = 0;

        loop {
            let mut buffer = Vec::new();
            buffer.resize(CHUNK_SIZE, 0);

            let read_bytes = file.read(&mut buffer).unwrap();

            if read_bytes == 0 {
                break;
            }

            buffer.truncate(read_bytes);

            jobs_tx.send(Job { data: buffer }).unwrap();
            jobs_in_flight += 1;

            for result in results_rx.try_iter() {
                total_stats.add(&result);
                jobs_in_flight -= 1;
                let elapsed = std::time::Instant::now() - start;
                eprint!(
                    "\rAvg pace: {:.1} MB / s",
                    total_stats.scanned_bytes as f64 / 1000000.0 / elapsed.as_secs_f64()
                );
            }
        }

        std::mem::drop(jobs_tx);

        while jobs_in_flight > 0 {
            let result = results_rx.recv().unwrap();
            total_stats.add(&result);
            jobs_in_flight -= 1;
        }
        let elapsed = std::time::Instant::now() - start;
        eprintln!(
            "\rAvg pace: {:.1} MB / s",
            total_stats.scanned_bytes as f64 / 1000000.0 / elapsed.as_secs_f64()
        );

        while !join_handles.is_empty() {
            join_handles.pop().unwrap().join().unwrap();
        }
    });

    total_stats
}

fn format_token(s: &[u8]) -> String {
    match String::from_utf8(s.to_vec()) {
        Ok(string) => format!("{:?}", string),
        Err(_) => format!("{:?}", s),
    }
}

fn optimize_bpe(token_set: &TokenSet, ntokens: usize, filename: &str) -> (TokenSet, TokenStats) {
    let mut token_set = token_set.clone();
    let mut prev_stats = None;
    let mut initial_stats = TokenStats::new(&token_set);

    loop {
        initial_stats = match prev_stats {
            Some(s) => s,
            None => tokenize_file(&token_set, filename),
        };

        let mut top_literal = 0;
        let mut top_literal_count = 0;

        for i in 0..256 {
            if initial_stats.token_count[i] > top_literal_count {
                top_literal = i;
                top_literal_count = initial_stats.token_count[i];
            }
        }

        println!(
            "Top literal: {} with count {}",
            top_literal, top_literal_count
        );

        let mut top_pair = 0;
        let mut top_pair_count = 0;
        for ipair in 0..initial_stats.pair_count.len() {
            if initial_stats.pair_count[ipair] > top_pair_count {
                top_pair = ipair;
                top_pair_count = initial_stats.pair_count[ipair];
            }
        }

        let ifirst = top_pair / token_set.ntokens;
        let isecond = top_pair % token_set.ntokens;

        let mut token_str = token_set.tokens[ifirst].string.clone();
        token_str.extend(token_set.tokens[isecond].string.clone());

        println!(
            "Top pair: {} with count {}",
            format_token(&token_str),
            top_pair_count
        );

        let new_token_str = if top_literal_count > top_pair_count {
            vec![top_literal as u8]
        } else {
            token_str
        };

        let mut new_token_set = token_set.clone();
        new_token_set.add_token(&new_token_str);
        prev_stats = None;

        println!(
            "{} Adding token {}",
            initial_stats.cost,
            format_token(&new_token_str)
        );

        if new_token_set.ntokens > 256 + ntokens {
            let stats = tokenize_file(&new_token_set, filename);
            let mut token_ids: Vec<usize> = (0..new_token_set.tokens.len()).collect();
            token_ids.sort_unstable_by_key(|&i| stats.token_count[i]);

            let mut found = false;
            let mut tries = 0;

            for &token_id_to_remove in token_ids.iter() {
                let token_to_remove = &new_token_set.tokens[token_id_to_remove];
                if token_to_remove.is_literal || token_to_remove.is_mandatory {
                    continue;
                }
                tries += 1;
                let token_str = token_to_remove.string.clone();

                new_token_set.remove_token(token_id_to_remove);

                let stats = tokenize_file(&new_token_set, filename);

                if stats.cost < initial_stats.cost {
                    // Found a token to remove.
                    found = true;
                    prev_stats = Some(stats);
                    println!(
                        "Removing token {} after {} tries",
                        format_token(&token_str),
                        tries
                    );
                    break;
                }

                new_token_set.add_token(&token_str);
            }

            if !found {
                break;
            }
        }

        token_set = new_token_set;
    }

    (token_set, initial_stats)
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

    let mut fallback16 = false;

    let token_set = if args.input.is_empty() {
        TokenSet::build_with_bin_literals()
    } else {
        let contents = std::fs::read_to_string(args.input).unwrap();
        let parsed = json::parse(&contents).unwrap();

        fallback16 = parsed["config"]["fallback16"].as_bool().unwrap();

        let mut token_set = if fallback16 {
            TokenSet::build_with_hex_literals()
        } else {
            TokenSet::build_with_bin_literals()
        };

        for token_str in parsed["tokens"].members() {
            if token_str.is_string() {
                token_set.add_token(token_str.as_str().unwrap().as_bytes());
            } else {
                let mut s = vec![];
                for b in token_str.members() {
                    s.push(b.as_u8().unwrap());
                }
                token_set.add_token(&s);
            }
        }

        token_set
    };

    let tokens_json = token_set.to_json();
    println!("{}", json::stringify(tokens_json));

    let filename = args.data.as_str();

    let (token_set, token_stats) = optimize_bpe(&token_set, args.ntokens, filename);

    let mut tokens_json = token_set.to_json();

    tokens_json["stats"]["ntokens"] = (token_set.ntokens - 256).into();
    tokens_json["stats"]["scanned_bytes"] = token_stats.scanned_bytes.into();
    tokens_json["stats"]["total_tokens"] = token_stats.cost.into();
    tokens_json["stats"]["bytes_per_token"] =
        (token_stats.scanned_bytes as f64 / token_stats.cost as f64).into();
    tokens_json["config"]["fallback16"] = fallback16.into();

    let tokens_json_str = json::stringify_pretty(tokens_json, 2);
    println!("{}", &tokens_json_str);

    if !args.output.is_empty() {
        std::fs::write(args.output, &tokens_json_str).unwrap();
    }
}
