#!/usr/bin/env python3
import asyncio
import aiohttp
import time
import sys

async def main():
    if len(sys.argv) < 2:
        print("Usage: python benchmark.py <load_balancer_base_url>")
        print("Example: python benchmark.py http://98.87.148.211")
        sys.exit(1)

    base_url = sys.argv[1]
    num_requests = 1000

if __name__ == "__main__":
    asyncio.run(main())