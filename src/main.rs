use std::env;
use std::fs::File;
use std::io::{self, Read, BufReader, BufRead, Seek};
use std::collections::HashMap;


fn main() -> io::Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 2 {
        eprintln!("Usage: {} <file_path>", args[0]);
        std::process::exit(1);
    }

    let file_path = &args[1];
    let file = File::open(file_path)?;
    let reader = BufReader::new(file);
    // let bytes = reader.bytes().map(|r| r.unwrap());
    // count_bytes(bytes);
    count_chars(reader);

    Ok(())
}

fn count_bytes<I: IntoIterator<Item = u8>>(bytes: I) {
    let mut counts: [usize; 256] = [0; 256];

    for b in bytes {
        counts[b as usize] += 1;
    }

    for b in 0..256 {
        println!("{:02x}  {}", b, counts[b]);
    }
}

fn count_chars<R: Read>(reader: BufReader<R>) {
    let mut char_count = HashMap::new();

    for line_result in reader.lines() {
        match line_result {
            Ok(line) => {
                for character in line.chars() {
                    // Increment the count for this character in the HashMap
                    *char_count.entry(character).or_insert(0) += 1;
                }
            },
            Err(error) => {
                eprintln!("Error reading line: {}", error);
            }
        }
    }

    for i in 0xE000..0xE020 {
        let character = char::from_u32(i).unwrap();
        if let Some(count) = char_count.get(&character) {
            println!("'{}' ({:x}): {}", character, i, *count);
        }
    }

}