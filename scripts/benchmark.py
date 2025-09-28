#!/usr/bin/env python3
import asyncio
import aiohttp
import time
import sys

async def run_benchmark(base_url: str, cluster_path: str, num_requests: int):
    url = f"{base_url}{cluster_path}"
    print(f"\n--- Benchmarking {cluster_path} with {num_requests} requests ---")
    print(f"Target URL: {url}")

    start_time = time.time()
    end_time = time.time()

    total_time = end_time - start_time
    print("\n--- Results ---")
    print(f"Total time taken:      {total_time:.2f} seconds")
    print("-----------------")

async def main():
    if len(sys.argv) < 2:
        print("Usage: python benchmark.py <load_balancer_base_url>")
        print("Example: python benchmark.py http://98.87.148.211")
        sys.exit(1)

    base_url = sys.argv[1]
    num_requests = 1000

if __name__ == "__main__":
    asyncio.run(main())