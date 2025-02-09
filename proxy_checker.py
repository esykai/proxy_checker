import sys
import aiohttp
import asyncio
import time

from typing import List
from dataclasses import dataclass
from aiohttp_socks import ProxyConnector


@dataclass
class ProxyStats:
    url: str
    speed: float
    protocol: str
    last_checked: float
    is_working: bool = False


class ProxyChecker:
    def __init__(self, test_url: str = "http://www.google.com", timeout: float = 1.0):
        self.test_url = test_url
        self.timeout = timeout
        self.results: List[ProxyStats] = []
        self.checked_count = 0
        self.total_count = 0

    async def fetch_proxy_lists(self, urls: List[str]) -> List[str]:
        async with aiohttp.ClientSession() as session:
            tasks = []
            for url in urls:
                tasks.append(self.fetch_single_list(session, url))
            results = await asyncio.gather(*tasks, return_exceptions=True)

            proxy_lists = []
            for result in results:
                if isinstance(result, list):
                    proxy_lists.extend(result)
            return list(set(proxy_lists))

    async def fetch_single_list(self, session: aiohttp.ClientSession, url: str) -> List[str]:
        try:
            async with session.get(url, timeout=self.timeout) as response:
                if response.status == 200:
                    content = await response.text()
                    return content.strip().split('\n')
        except Exception as e:
            print(f"Ошибка загрузки {url}: {str(e)}", file=sys.stderr)
            return []

    def update_progress(self):
        self.checked_count += 1
        percent = (self.checked_count / self.total_count) * 100
        print(f"\rПроверено: {self.checked_count}/{self.total_count} ({percent:.1f}%)", end="", flush=True)

    async def check_proxy(self, proxy: str) -> ProxyStats:
        protocol = "http"
        if "socks4://" in proxy.lower():
            protocol = "socks4"
        elif "socks5://" in proxy.lower():
            protocol = "socks5"

        if not proxy.startswith(('http://', 'socks4://', 'socks5://')):
            proxy = f"http://{proxy}"

        try:
            start_time = time.time()
            connector = ProxyConnector.from_url(proxy)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(self.test_url, timeout=self.timeout) as response:
                    if response.status == 200:
                        speed = time.time() - start_time
                        print(f"\rПрокси работает: {proxy} - {speed:.2f}s")
                        self.update_progress()
                        return ProxyStats(
                            url=proxy,
                            speed=speed,
                            protocol=protocol,
                            last_checked=time.time(),
                            is_working=True
                        )
        except:
            pass

        self.update_progress()
        return ProxyStats(
            url=proxy,
            speed=float('inf'),
            protocol=protocol,
            last_checked=time.time(),
            is_working=False
        )

    async def check_proxies(self, proxies: List[str], max_concurrent: int = 1000):
        self.total_count = len(proxies)
        self.checked_count = 0
        print(f"Начинаем проверку {self.total_count} прокси...")

        tasks = []
        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded_check(proxy):
            async with semaphore:
                return await self.check_proxy(proxy)

        for proxy in proxies:
            if proxy.strip():
                tasks.append(asyncio.create_task(bounded_check(proxy)))

        self.results = await asyncio.gather(*tasks, return_exceptions=True)
        self.results = [r for r in self.results if isinstance(r, ProxyStats)]

    def get_best_proxies(self, limit: int = None) -> List[ProxyStats]:
        working_proxies = [p for p in self.results if p.is_working]
        sorted_proxies = sorted(working_proxies, key=lambda x: x.speed)
        return sorted_proxies[:limit] if limit else sorted_proxies

    def save_working_proxies(self, filename: str = "output.txt"):
        working_proxies = self.get_best_proxies()
        with open(filename, 'w', encoding='utf-8') as f:
            for proxy in working_proxies:
                f.write(f"{proxy.url}\n")
        print(f"\nРабочие прокси сохранены в файл {filename}")


async def load_urls_from_file(filename: str) -> List[str]:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Файл {filename} не найден!")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка при чтении файла {filename}: {str(e)}")
        sys.exit(1)


async def main():
    start_time = time.time()
    checker = ProxyChecker(timeout=1.0)

    print("Загрузка ссылок из файла...")
    urls = await load_urls_from_file('links.txt')
    print(f"Загружено {len(urls)} ссылок")

    print("Загрузка списков прокси...")
    proxies = await checker.fetch_proxy_lists(urls)
    print(f"Найдено {len(proxies)} уникальных прокси")

    print("Проверка прокси...")
    await checker.check_proxies(proxies)

    # Сохраняем все рабочие прокси
    checker.save_working_proxies('output.txt')

    # Выводим топ 10 самых быстрых для информации
    best_proxies = checker.get_best_proxies(10)
    print("\nТоп 10 самых быстрых прокси:")
    for i, proxy in enumerate(best_proxies, 1):
        print(f"{i}. {proxy.url} - {proxy.protocol} - {proxy.speed:.2f}s")

    total_time = time.time() - start_time
    working_count = len([p for p in checker.results if p.is_working])
    print(f"\nВремя выполнения: {total_time:.2f} секунд")
    print(f"Всего рабочих прокси: {working_count}")


if __name__ == "__main__":
    asyncio.run(main())
