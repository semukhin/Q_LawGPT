from typing import Dict, Any, List, Optional
import logging
import asyncio
from app.core.config import settings
from app.rag.retrieval import document_retriever
from app.services.ai_service import call_qwen_api
from app.services.elasticsearch_service import elasticsearch_service

logger = logging.getLogger(__name__)

class LegalNormsAgent:
    """
    Агент, специализирующийся на правовых нормах (законах, постановлениях, кодексах)
    """
    
    def __init__(self):
        self.es_service = elasticsearch_service
    
    async def search_legal_norms(self, query: str) -> List[Dict[str, Any]]:
        """
        Поиск релевантных правовых норм на основе запроса
        """
        # Поиск в ElasticSearch через сервис
        laws_results = self.es_service.search_law_chunks(query, top_n=7)
        
        # Если результатов мало, можно добавить поиск в интернете
        if not laws_results or len(laws_results) < 3:
            logger.info(f"Недостаточно результатов в базе данных для запроса: {query}. Требуется внешний поиск.")
            # Здесь можно реализовать поиск в интернете через Google Programmatic Search
            # Например: 
            # web_results = await self._search_web(query + " закон норма правовой")
            # laws_results.extend(web_results)
        
        return laws_results
    
    async def analyze_legal_norms(self, query: str, legal_norms: List[Dict[str, Any]]) -> str:
        """
        Анализ правовых норм, релевантных запросу
        """
        system_prompt = """
        Вы - специализированный юридический агент по правовым нормам Российской Федерации. Ваша задача - 
        проанализировать запрос пользователя и предоставить информацию о релевантных правовых нормах.
        
        Ваш ответ должен:
        1. Определить ключевые законы, кодексы и нормативные акты, относящиеся к запросу
        2. Процитировать и объяснить релевантные статьи и положения
        3. Предоставить структурированный анализ нормативной базы
        
        Ваш ответ должен быть профессиональным, точным и основанным на актуальном российском законодательстве.
        """
        
        # Подготовка контекста с правовыми нормами
        context = "Результаты поиска по правовым нормам:\n\n"
        
        if legal_norms:
            for i, law in enumerate(legal_norms):
                context += f"{i+1}. {law}\n\n"
        else:
            context += "Не найдено релевантных правовых норм в базе данных.\n\n"
        
        user_message = f"Запрос пользователя: {query}\n\n{context}\n\nПроанализируйте правовые нормы, относящиеся к запросу."
        
        # Вызов общей функции API
        result = await call_qwen_api(
            prompt=user_message,
            system_message=system_prompt,
            max_tokens=2000
        )
        
        if result["success"]:
            return result["text"]
        else:
            return f"Произошла ошибка при анализе правовых норм: {result.get('error', 'Неизвестная ошибка')}"

    async def _search_web(self, query: str) -> List[Dict[str, Any]]:
        """
        Поиск правовых норм в интернете
        """
        from app.agents.analytics import AnalyticsAgent
        # Использование метода поиска из AnalyticsAgent
        analytics_agent = AnalyticsAgent()
        return await analytics_agent._search_google(query + " правовая норма закон кодекс")
    
    async def process_query(self, query: str) -> Dict[str, Any]:
        """
        Обработка запроса и возврат анализа правовых норм
        """
        try:
            # Поиск релевантных правовых норм
            legal_norms = await self.search_legal_norms(query)
            
            # Анализ правовых норм
            analysis = await self.analyze_legal_norms(query, legal_norms)
            
            return {
                "legal_norms": legal_norms,
                "analysis": analysis
            }
        except Exception as e:
            logger.error(f"Ошибка обработки запроса в агенте правовых норм: {str(e)}")
            return {"error": str(e)}

# Создание экземпляра-синглтона
legal_norms_agent = LegalNormsAgent()