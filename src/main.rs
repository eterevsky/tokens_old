use std::env;
use std::fs::File;
use std::io::{self, Read, BufReader};

fn main() -> io::Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 2 {
        eprintln!("Usage: {} <file_path>", args[0]);
        std::process::exit(1);
    }

    let file_path = &args[1];
    let file = File::open(file_path)?;
    let reader = BufReader::new(file);
    let bytes = reader.bytes().map(|r| r.unwrap());
    count_bytes(bytes);

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