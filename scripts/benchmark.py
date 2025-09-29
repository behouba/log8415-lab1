#!/usr/bin/env python3
import asyncio
import aiohttp
import time
import sys

async def call_endpoint(session, url, request_num):
    try:
        async with session.get(url) as response:
            # We don't need the body, just that it succeeded
            if response.status == 200:
                return True
            else:
                print(f"Request {request_num}: Failed with status code {response.status}")
                return False
    except Exception as e:
        print(f"Request {request_num}: Failed with exception {e}")
        return False

async def run_benchmark(base_url: str, cluster_path: str, num_requests: int):
    url = f"{base_url}{cluster_path}"
    print(f"\n--- Benchmarking {cluster_path} with {num_requests} requests ---")
    print(f"Target URL: {url}")
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        tasks = [call_endpoint(session, url, i) for i in range(num_requests)]
        results = await asyncio.gather(*tasks)
        
    end_time = time.time()
    
    total_time = end_time - start_time
    successful_requests = sum(1 for r in results if r)
    failed_requests = num_requests - successful_requests
    avg_time_per_request = total_time / num_requests
    requests_per_second = successful_requests / total_time if total_time > 0 else 0
    
    print("\n--- Results ---")
    print(f"Total time taken:      {total_time:.2f} seconds")
    print(f"Successful requests:   {successful_requests}/{num_requests}")
    print(f"Failed requests:       {failed_requests}")
    print(f"Requests per second:   {requests_per_second:.2f} RPS")
    print(f"Avg. time per request: {avg_time_per_request * 1000:.2f} ms")
    print("-----------------")

async def main():
    if len(sys.argv) < 2:
        print("Usage: python benchmark.py <load_balancer_base_url>")
        print("Example: python benchmark.py http://98.87.148.211")
        sys.exit(1)
        
    base_url = sys.argv[1]
    num_requests = 1000
    
    await run_benchmark(base_url, "/cluster1", num_requests)
    await run_benchmark(base_url, "/cluster2", num_requests)

if __name__ == "__main__":
    asyncio.run(main())