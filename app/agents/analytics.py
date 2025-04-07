from typing import Dict, Any, List, Optional
import logging
import aiohttp
import json
import asyncio
from app.core.config import settings
from app.rag.retrieval import document_retriever
from app.services.ai_service import call_qwen_api
from app.services.elasticsearch_service import elasticsearch_service

logger = logging.getLogger(__name__)

class AnalyticsAgent:
    """
    Agent specialized in legal analytics (commentaries, articles, books)
    """
    
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = "qwen/qwen2.5-vl-72b-instruct:free"
        self.google_search_api_key = settings.GOOGLE_SEARCH_API_KEY
        self.google_search_cx = settings.GOOGLE_SEARCH_CX
        self.es_service = elasticsearch_service
    
    async def search_legal_analytics(self, query: str) -> Dict[str, Any]:
        """
        Search for relevant legal analytics based on the query
        """
        # Search in ElasticSearch through service
        analytics_results = self.es_service.search_law_chunks(query, top_n=5)
        
        # If insufficient results, supplement with Google Search
        if len(analytics_results) < 3:
            google_results = await self._search_google(query + " правовой анализ")
            analytics_results.extend(google_results)
        
        return analytics_results
    
    async def _search_google(self, query: str) -> List[Dict[str, Any]]:
        """
        Search using Google Programmatic Search API
        """
        if not self.google_search_api_key or not self.google_search_cx:
            logger.warning("Google Search API credentials not configured")
            return []
        
        google_search_url = "https://www.googleapis.com/customsearch/v1"
        
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "key": self.google_search_api_key,
                    "cx": self.google_search_cx,
                    "q": query,
                    "num": 5
                }
                
                async with session.get(google_search_url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"Error in Google Search API: {await response.text()}")
                        return []
                    
                    result = await response.json()
                    
                    # Format Google results to match our internal format
                    formatted_results = []
                    for item in result.get("items", []):
                        formatted_results.append({
                            "title": item.get("title", ""),
                            "content_snippet": item.get("snippet", ""),
                            "source": "Google Search",
                            "url": item.get("link", ""),
                            "publication_date": item.get("pagemap", {}).get("metatags", [{}])[0].get("date", "")
                        })
                    
                    return formatted_results
        except Exception as e:
            logger.error(f"Error in Google Search: {str(e)}")
            return []
    
    async def analyze_legal_analytics(self, query: str, analytics_results: List[Dict[str, Any]]) -> str:
        """
        Analyze legal analytics relevant to the query
        """
        system_prompt = """
        Вы - специализированный юридический агент по аналитике и комментариям к российскому законодательству. 
        Ваша задача - проанализировать запрос пользователя и предоставить информацию на основе юридических 
        комментариев, статей, книг и других аналитических материалов.
        
        Ваш ответ должен:
        1. Определить ключевые точки зрения и мнения экспертов по рассматриваемому вопросу
        2. Представить различные подходы к решению вопроса
        3. Обобщить аналитические выводы и рекомендации экспертов
        4. Указать на тенденции в развитии юридической мысли по данному вопросу
        
        Ваш ответ должен быть профессиональным, взвешенным и основанным на экспертных мнениях.
        """
        
        # Prepare context with analytics results
        context = "Результаты поиска по аналитическим материалам:\n\n"
        
        if analytics_results:
            for i, analytics in enumerate(analytics_results):
                context += f"{i+1}. {analytics}\n\n"
        else:
            context += "Не найдено релевантных аналитических материалов.\n\n"
        
        user_message = f"Запрос пользователя: {query}\n\n{context}\n\nПроанализируйте аналитические материалы, относящиеся к запросу."
        
        try:
            result = call_qwen_api(
                prompt=user_message,
                system_message=system_prompt,
                api_key=self.api_key,
                max_tokens=2000,
                temperature=0.7
            )
            
            if not result["success"]:
                logger.error(f"Error calling Qwen API: {result.get('error', 'Unknown error')}")
                return f"Произошла ошибка при анализе аналитических материалов: {result.get('error', 'Unknown error')}"
            
            return result["text"]
        except Exception as e:
            logger.error(f"Error in analytics agent: {str(e)}")
            return f"Произошла ошибка при анализе аналитических материалов: {str(e)}"
    
    async def process_query(self, query: str) -> Dict[str, Any]:
        """
        Process the query and return analytics analysis
        """
        try:
            # Search for relevant analytics
            analytics_results = await self.search_legal_analytics(query)
            
            # Analyze analytics
            analysis = await self.analyze_legal_analytics(query, analytics_results)
            
            return {
                "analytics_results": analytics_results,
                "analysis": analysis
            }
        except Exception as e:
            logger.error(f"Error processing query in analytics agent: {str(e)}")
            return {"error": str(e)}

    async def analyze_information(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Анализирует юридическую информацию и предоставляет инсайты
        """
        system_prompt = """
        Вы - специалист по анализу юридической информации. Ваша задача - проанализировать
        предоставленную информацию и выявить ключевые моменты, тенденции и закономерности.
        
        Анализ должен включать:
        1. Основные выводы
        2. Ключевые тенденции
        3. Важные прецеденты
        4. Рекомендации
        """
        
        user_message = f"""
        Запрос: {query}
        
        Контекст:
        {json.dumps(context, ensure_ascii=False, indent=2)}
        
        Пожалуйста, проанализируйте информацию и предоставьте структурированный анализ.
        """
        
        try:
            result = call_qwen_api(
                prompt=user_message,
                system_message=system_prompt,
                api_key=self.api_key,
                max_tokens=4000,
                temperature=0.7
            )
            
            if not result["success"]:
                logger.error(f"Error calling Qwen API: {result.get('error', 'Unknown error')}")
                return {"error": f"API Error: {result.get('error', 'Unknown error')}"}
            
            return {
                "analysis": result["text"],
                "metadata": {
                    "query": query,
                    "context": context
                }
            }
        except Exception as e:
            logger.error(f"Error in information analysis: {str(e)}")
            return {"error": str(e)}

# Create singleton instance
analytics_agent = AnalyticsAgent()