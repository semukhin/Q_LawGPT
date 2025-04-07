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

class JudicialPracticeAgent:
    """
    Agent specialized in judicial practice (court decisions, case reviews)
    """
    
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = "qwen/qwen2.5-vl-72b-instruct:free"
        self.es_service = elasticsearch_service
    
    async def search_judicial_practice(self, query: str) -> Dict[str, Any]:
        """
        Search for relevant judicial practice based on the query
        """
        # Search in ElasticSearch through service
        court_decisions = self.es_service.search_law_chunks(query, top_n=7)
        
        # Prepare search results for agent
        context = "Результаты поиска по судебной практике:\n\n"
        
        if court_decisions:
            for i, decision in enumerate(court_decisions):
                context += f"{i+1}. {decision}\n\n"
        else:
            context += "Не найдено релевантной судебной практики. Необходимо обратиться к внешнему поиску.\n\n"
            # Here we would implement web search using the Google Programmatic Search
        
        return court_decisions
    
    async def analyze_judicial_practice(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Анализирует судебную практику и решения судов
        """
        system_prompt = """
        Вы - специалист по анализу судебной практики. Ваша задача - проанализировать
        предоставленные судебные решения и выявить ключевые моменты, тенденции и закономерности.
        
        Анализ должен включать:
        1. Основные правовые позиции судов
        2. Ключевые аргументы
        3. Применяемые нормы права
        4. Выводы и рекомендации
        """
        
        user_message = f"""
        Запрос: {query}
        
        Контекст:
        {json.dumps(context, ensure_ascii=False, indent=2)}
        
        Пожалуйста, проанализируйте судебную практику и предоставьте структурированный анализ.
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
            logger.error(f"Error in judicial practice analysis: {str(e)}")
            return {"error": str(e)}
    
    async def process_query(self, query: str) -> Dict[str, Any]:
        """
        Process the query and return judicial practice analysis
        """
        try:
            # Search for relevant judicial practice
            court_decisions = await self.search_judicial_practice(query)
            
            # Analyze judicial practice
            analysis = await self.analyze_judicial_practice(query, court_decisions)
            
            return {
                "court_decisions": court_decisions,
                "analysis": analysis
            }
        except Exception as e:
            logger.error(f"Error processing query in judicial practice agent: {str(e)}")
            return {"error": str(e)}

# Create singleton instance
judicial_practice_agent = JudicialPracticeAgent()