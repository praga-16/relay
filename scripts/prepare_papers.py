import argparse
from app.retrieval.ingest import prepare, extract

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Embedded version only; NOT official verification")
    args = parser.parse_args()
    print(prepare(download=not args.offline))
    print("Extracted paragraphs:", len(extract()))
