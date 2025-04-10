import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Any, Tuple
import logging
from urllib.parse import urlparse, urljoin
import re
import time
import ssl
import json
import hashlib
import os
from datetime import datetime
import trafilatura
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ScrapedContent:
    """Контейнер для скрейпинга веб-страниц."""
    url: str
    title: str
    text: str
    html: str
    metadata: Dict[str, Any]
    timestamp: datetime = datetime.now()
    content_type: str = "text/html"
    status_code: Optional[int] = None
    error: Optional[str] = None
    scrape_start_time: Optional[float] = None
    scrape_end_time: Optional[float] = None
    content_size: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь для сериализации."""
        result = {
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "html": self.html,
            "metadata": self.metadata,
            "content_type": self.content_type,
            "status_code": self.status_code,
            "error": self.error,
            "scrape_start_time": self.scrape_start_time,
            "scrape_end_time": self.scrape_end_time,
            "content_size": self.content_size
        }
        
        if isinstance(self.timestamp, datetime):
            result["timestamp"] = self.timestamp.isoformat()
        else:
            result["timestamp"] = self.timestamp
            
        return result

    def is_successful(self) -> bool:
        """Проверка успешности скрейпинга."""
        return self.error is None and bool(self.text.strip())
    
    @staticmethod
    def from_error(url: str, error_msg: str) -> 'ScrapedContent':
        """Создание объекта с информацией об ошибке."""
        return ScrapedContent(
            url=url,
            title="Error",
            text="",
            html="",
            metadata={"error_type": "robots_txt_denied" if "denied by robots.txt" in error_msg else "general_error"},
            content_type="text/plain",
            error=error_msg,
            status_code=None,
            scrape_start_time=time.time(),
            scrape_end_time=time.time()
        )

class ScraperCache:
    """Кэш для скрейпинга для улучшения производительности."""
    def __init__(self, cache_dir: Optional[str] = None, ttl: int = 86400):
        self.cache_dir = cache_dir or os.path.expanduser("~/.q_lawgpt/cache/scraper")
        self.ttl = ttl
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def _get_cache_key(self, url: str) -> str:
        """Генерация ключа кэша из URL."""
        return hashlib.md5(url.encode()).hexdigest()
    
    def _get_cache_path(self, key: str) -> str:
        """Получение пути к файлу кэша."""
        return os.path.join(self.cache_dir, f"{key}.json")
    
    def get(self, url: str) -> Optional[ScrapedContent]:
        """Получение кэшированного контента, если доступен и не истек срок."""
        key = self._get_cache_key(url)
        path = self._get_cache_path(key)
        
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                
                if time.time() - data['timestamp'] <= self.ttl:
                    content_dict = data['content']
                    required_fields = ['url', 'title', 'text', 'html', 'metadata']
                    if all(field in content_dict for field in required_fields):
                        if 'timestamp' in content_dict:
                            content_dict['timestamp'] = datetime.fromisoformat(content_dict['timestamp'])
                        return ScrapedContent(**content_dict)
                    else:
                        logger.warning(f"Кэш для {url} отсутствует необходимые поля. Инвалидация кэша.")
                        os.remove(path)
            except Exception as e:
                logger.error(f"Ошибка чтения кэша для {url}: {e}")
        
        return None
    
    def set(self, content: ScrapedContent):
        """Кэширование скрейпинга."""
        if not isinstance(content, ScrapedContent):
            raise ValueError("Только объекты ScrapedContent могут быть кэшированы.")
        key = self._get_cache_key(content.url)
        path = self._get_cache_path(key)
        
        try:
            with open(path, 'w') as f:
                json.dump({
                    'timestamp': time.time(),
                    'content': content.to_dict()
                }, f)
        except Exception as e:
            logger.error(f"Ошибка записи кэша для {content.url}: {e}")

class WebSearchService:
    def __init__(self, max_concurrent: int = 8, cache_ttl: int = 86400):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }
        self.max_concurrent = max_concurrent
        self.cache = ScraperCache(ttl=cache_ttl)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
    async def _get_page_simple(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """Получение содержимого страницы с помощью aiohttp с улучшенным определением кодировки."""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    url, 
                    headers=self.headers,
                    ssl=ssl_context,
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as response:
                    content_type = response.headers.get('Content-Type', 'text/html')
                    status_code = response.status
                    
                    if 200 <= status_code < 300:
                        try:
                            html_text = await response.text()
                            return html_text, content_type, status_code
                        except UnicodeDecodeError:
                            content = await response.read()
                            for encoding in ['windows-1251', 'cp1251', 'latin-1', 'iso-8859-1']:
                                try:
                                    html_text = content.decode(encoding)
                                    return html_text, content_type, status_code
                                except UnicodeDecodeError:
                                    continue
                            
                            return content.decode('utf-8', errors='replace'), content_type, status_code
                    else:
                        logger.error(f"HTTP ошибка {status_code} для {url}")
                        return None, content_type, status_code
            except asyncio.TimeoutError:
                logger.error(f"Таймаут при получении {url}")
                return None, None, None
            except Exception as e:
                logger.error(f"Ошибка при получении {url}: {e}")
                return None, None, None

    def _extract_content(self, html: str, url: str, content_type: str = "text/html") -> Dict[str, Any]:
        """Извлечение контента из HTML с использованием trafilatura или BeautifulSoup."""
        if not html:
            return {
                "title": "Нет контента",
                "text": "",
                "metadata": {"url": url}
            }
        
        try:
            extracted_text = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=True,
                include_images=False,
                include_links=False,
                output_format="txt"
            )
            
            if extracted_text and len(extracted_text.strip()) > 100:
                soup = BeautifulSoup(html, 'html.parser')
                title = soup.title.string if soup.title else url.split("/")[-1]
                
                return {
                    "title": title,
                    "text": extracted_text,
                    "metadata": {"url": url}
                }
            
            # Fallback to BeautifulSoup if trafilatura fails
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove unwanted elements
            for elem in soup.select('script, style, nav, footer, header, .sidebar, .navigation, .menu, .ad, .advertisement'):
                elem.decompose()
            
            title = ""
            if soup.title:
                title = soup.title.string
            
            # Extract main content
            main_content = []
            for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li']:
                for element in soup.find_all(tag):
                    text = element.get_text(strip=True)
                    if text:
                        if tag.startswith('h'):
                            level = int(tag[1])
                            prefix = '#' * level
                            main_content.append(f"{prefix} {text}")
                        else:
                            main_content.append(text)
            
            text = "\n\n".join(main_content)
            
            # Extract metadata
            metadata = {
                "description": "",
                "keywords": "",
                "author": "",
                "date": "",
                "publisher": "",
                "language": "",
                "url": url
            }
            
            meta_tags = soup.find_all('meta')
            for tag in meta_tags:
                if tag.get('name') and tag.get('content'):
                    name = tag['name'].lower()
                    if name in metadata:
                        metadata[name] = tag['content']
            
            return {
                "title": title,
                "text": text,
                "metadata": metadata
            }
            
        except Exception as e:
            logger.error(f"Ошибка извлечения контента для {url}: {e}")
            return {
                "title": url.split("/")[-1] or "Неизвестный заголовок",
                "text": html[:1000] + "...",
                "metadata": {"url": url, "extraction_failed": True}
            }

    async def scrape_url(self, url: str, force_refresh: bool = False) -> ScrapedContent:
        """Скрейпинг контента с URL с кэшированием и улучшенной обработкой ошибок."""
        scrape_start = time.time()
        
        # Check cache first
        if not force_refresh:
            cached_content = self.cache.get(url)
            if cached_content:
                return cached_content
        
        html = None
        content_type = None
        status_code = None
        
        # Try to fetch the content with retries
        for attempt in range(3):
            try:
                html, content_type, status_code = await self._get_page_simple(url)
                if html:
                    break
            except Exception as e:
                delay = (attempt + 1) * 2
                logger.warning(f"Попытка {attempt + 1} не удалась для {url}: {e}")
                logger.warning(f"Ожидание {delay} секунд...")
                await asyncio.sleep(delay)
        
        if not html:
            error_msg = f"Не удалось получить контент после 3 попыток"
            return ScrapedContent.from_error(url, error_msg)
            
        content = self._extract_content(html, url, content_type)
        
        result = ScrapedContent(
            url=url,
            title=content["title"],
            text=content["text"],
            html=html,
            metadata=content["metadata"],
            content_type=content_type or "text/html",
            status_code=status_code,
            scrape_start_time=scrape_start,
            scrape_end_time=time.time(),
            content_size=len(html) if html else 0
        )
        
        if result.is_successful():
            try:
                self.cache.set(result)
            except Exception as e:
                logger.error(f"Не удалось кэшировать контент для {url}: {e}")
            
        return result

    async def search_articles(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Поиск статей по запросу."""
        search_url = f"https://html.duckduckgo.com/html/?q={query}"
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(search_url) as response:
                    if response.status == 200:
                        html = await response.text()
                        return await self._parse_search_results(html, max_results)
                    else:
                        logger.error(f"Ошибка поиска: {response.status}")
                        return []
            except Exception as e:
                logger.error(f"Ошибка при выполнении поиска: {str(e)}")
                return []

    async def _parse_search_results(self, html: str, max_results: int) -> List[Dict[str, str]]:
        """Парсинг результатов поиска."""
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        
        for result in soup.select('.result')[:max_results]:
            title_elem = result.select_one('.result__title')
            link_elem = result.select_one('.result__url')
            
            if title_elem and link_elem:
                title = title_elem.get_text(strip=True)
                url = link_elem.get('href')
                if url:
                    results.append({
                        'title': title,
                        'url': url
                    })
        
        return results

    async def search_and_scrape(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Комбинированный метод для поиска и скрейпинга статей."""
        # Поиск статей
        search_results = await self.search_articles(query, max_results)
        
        # Скрейпинг каждой найденной статьи
        scraped_articles = []
        for result in search_results:
            article = await self.scrape_url(result['url'])
            if article and article.is_successful():
                scraped_articles.append({
                    'title': article.title,
                    'url': article.url,
                    'content': article.text,
                    'metadata': article.metadata
                })
        
        return scraped_articles
    
    async def search_and_scrape_with_cache(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """
        Комбинированная функция для поиска и скрейпинга с кэшированием и робастной обработкой ошибок
        """
        try:
            # Поиск с помощью DuckDuckGo
            search_results = await self.search_articles(query, max_results + 3)  # Запрашиваем больше для подстраховки
            
            if not search_results:
                return []
            
            # Готовим список для результатов скрейпинга
            scraped_articles = []
            search_tasks = []
            
            # Создаем задачи для скрейпинга
            for result in search_results:
                url = result.get('url')
                if not url:
                    continue
                    
                # Проверяем кэш
                cached_content = self.cache.get(url)
                if cached_content and cached_content.is_successful():
                    # Используем кэшированный результат
                    scraped_articles.append({
                        'title': cached_content.title,
                        'url': cached_content.url,
                        'content': cached_content.text,
                        'metadata': cached_content.metadata,
                        'from_cache': True
                    })
                else:
                    # Добавляем в список задач для скрейпинга
                    search_tasks.append(self.scrape_url(url, force_refresh=False))
            
            # Запускаем скрейпинг с ограничением числа одновременных задач
            async with asyncio.Semaphore(self.max_concurrent):
                scraped_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            # Обрабатываем результаты скрейпинга
            for result in scraped_results:
                # Пропускаем ошибки
                if isinstance(result, Exception):
                    continue
                    
                if not result or not result.is_successful():
                    continue
                    
                scraped_articles.append({
                    'title': result.title,
                    'url': result.url,
                    'content': result.text,
                    'metadata': result.metadata,
                    'from_cache': False
                })
                
                # Ограничиваем число результатов
                if len(scraped_articles) >= max_results:
                    break
            
            return scraped_articles[:max_results]
            
        except Exception as e:
            logger.error(f"Ошибка при поиске и скрейпинге: {str(e)}")
            return []
    
    async def analyze_web_results(self, query: str, web_results: List[Dict[str, Any]]) -> str:
        """
        Анализ результатов поиска в интернете с помощью Qwen
        """
        from app.services.ai_service import call_qwen_api
        
        system_prompt = """
        Вы - эксперт по юридическому анализу информации из интернета. Ваша задача - проанализировать 
        результаты веб-поиска и выделить ключевую информацию, релевантную запросу пользователя.
        
        Ваш анализ должен:
        1. Фокусироваться на правовых аспектах, релевантных для запроса
        2. Выделять основные факты и мнения
        3. Учитывать надежность источников
        4. Структурированно представлять информацию
        """
        
        # Формируем контекст из найденных статей
        context = "Найденные в интернете источники:\n\n"
        for i, result in enumerate(web_results, 1):
            context += f"Источник {i}: {result['title']} ({result['url']})\n"
            context += f"Содержание: {result['content'][:1000]}...\n\n"
        
        prompt = f"""
        Запрос пользователя: {query}
        
        {context}
        
        Пожалуйста, проанализируйте эти результаты поиска и предоставьте структурированную информацию, 
        которая поможет ответить на запрос пользователя.
        """
        
        try:
            response = await call_qwen_api(
                prompt=prompt,
                system_message=system_prompt,
                max_tokens=2000,
                temperature=0.4
            )
            
            if response["success"]:
                return response["text"]
            else:
                return "Не удалось проанализировать результаты поиска в интернете."
        except Exception as e:
            logger.error(f"Ошибка при анализе веб-результатов: {str(e)}")
            return f"Ошибка при анализе результатов поиска: {str(e)}"

    

# Создаем синглтон для использования в других частях приложения
web_search_service = WebSearchService() 