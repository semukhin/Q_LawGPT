from typing import List, Dict, Any, Optional
import logging
import json
import asyncio
from app.core.config import settings
from app.services.web_search import web_search_service
from app.services.ai_service import call_qwen_api
from app.services.elasticsearch_service import elasticsearch_service

logger = logging.getLogger(__name__)

class CoordinatorAgent:
    """
    Coordinator Agent responsible for orchestrating the workflow
    of other specialist agents
    """
    
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = "qwen/qwen2.5-vl-72b-instruct:free"  # Use the most capable model for coordination
        self.es_service = elasticsearch_service
    
    async def analyze_query(self, query: str, has_image: bool = False) -> Dict[str, Any]:
        """
        Анализирует запрос пользователя и определяет, каких агентов следует привлечь
        """
        
        # Сначала ищем релевантную правовую информацию
        legal_info = self.es_service.search_law_chunks(query, top_n=5)
        
        system_prompt = """
        Вы - координатор системы из специализированных юридических агентов. Ваша задача - проанализировать
        запрос пользователя и определить, какие агенты должны быть вовлечены в подготовку ответа и в каком порядке.
        
        Доступные агенты:
        1. legal_norms_agent - Специалист по правовым нормам (законы, постановления, кодексы)
        2. judicial_practice_agent - Специалист по судебной практике (решения судов, обзоры практики)
        3. analytics_agent - Специалист по аналитике (комментарии, статьи, книги)
        4. document_prep_agent - Специалист по подготовке документов (иски, жалобы, договоры)
        5. document_analysis_agent - Специалист по анализу изображений документов
        
        Проанализируйте запрос пользователя и определите:
        1. Какие агенты должны быть вовлечены (не всегда нужны все)
        2. В каком порядке они должны работать
        3. Какие уточняющие вопросы следует задать пользователю
        
        Ответьте в формате JSON:
        {
            "agents": ["agent1", "agent2"],
            "clarifying_questions": ["Вопрос 1?", "Вопрос 2?"],
            "plan": "Краткое описание плана подготовки ответа"
        }
        """
        
        # Если есть изображение, добавляем агент анализа документов
        if has_image:
            agents = ["document_analysis_agent"]
            # Если это только изображение без текста запроса, используем только анализ документов
            if not query or query.strip() == "":
                return {
                    "agents": agents,
                    "clarifying_questions": ["Какой аспект документа вас интересует?"],
                    "plan": "Анализ изображения документа"
                }
            # В противном случае продолжаем анализ запроса с учетом контекста документа

        # Формируем сообщение с учетом найденной правовой информации
        user_message = f"Запрос пользователя: {query}\n\n"
        if legal_info:
            user_message += "Найдена следующая релевантная правовая информация:\n"
            for i, info in enumerate(legal_info, 1):
                user_message += f"{i}. {info}\n\n"
        user_message += "Проанализируйте запрос и определите агентов и вопросы."
        
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
                return {"error": f"API Error: {result.get('error', 'Unknown error')}"}
            
            content = result["text"]
            # Extract JSON from the response
            try:
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                json_str = content[json_start:json_end]
                analysis = json.loads(json_str)
                return analysis
            except json.JSONDecodeError:
                logger.error(f"Error parsing JSON from response: {content}")
                # Fallback to default plan
                return {
                    "agents": ["legal_norms_agent", "judicial_practice_agent", "analytics_agent"],
                    "clarifying_questions": ["Уточните, пожалуйста, какие аспекты вашего вопроса наиболее важны?", 
                                             "Есть ли какие-то конкретные законы или нормативные акты, которые вас интересуют?"],
                    "plan": "Анализ правовых норм, изучение судебной практики, сбор аналитической информации"
                }
        except Exception as e:
            logger.error(f"Error in coordinator agent: {str(e)}")
            return {"error": str(e)}
    
    async def synthesize_response(self, query: str, agent_responses: Dict[str, Any]) -> str:
        """
        Synthesize the final response based on all agent outputs
        """
        # Получаем дополнительную правовую информацию для контекста
        legal_info = self.es_service.search_law_chunks(query, top_n=3)
        
        system_prompt = """
        Вы - координатор системы из специализированных юридических агентов. Ваша задача - синтезировать
        финальный ответ на основе результатов работы всех вовлеченных агентов.
        
        Ответ должен быть хорошо структурирован и содержать следующие разделы:
        1. Суть запроса
        2. Нормативная база
        3. Анализ
        4. Судебная практика (если применимо)
        5. Выводы
        6. Рекомендации
        
        Ответ должен быть профессиональным, информативным и полезным для пользователя.
        """
        
        # Prepare message with agent outputs
        user_message = f"Запрос пользователя: {query}\n\n"
        
        # Добавляем найденную правовую информацию
        if legal_info:
            user_message += "Релевантная правовая информация:\n"
            for i, info in enumerate(legal_info, 1):
                user_message += f"{i}. {info}\n\n"
        
        # Добавляем результаты работы агентов
        for agent_name, response in agent_responses.items():
            if response and not isinstance(response, str):
                response = json.dumps(response, ensure_ascii=False)
            user_message += f"Результат работы агента {agent_name}:\n{response}\n\n"
        
        user_message += "Пожалуйста, синтезируйте финальный ответ на запрос пользователя."
        
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
                return f"Произошла ошибка при синтезе ответа: {result.get('error', 'Unknown error')}"
            
            return result["text"]
        except Exception as e:
            logger.error(f"Error in coordinator agent synthesis: {str(e)}")
            return f"Произошла ошибка при синтезе ответа: {str(e)}"

    async def gather_web_info(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        Собирает информацию из веб-источников для обогащения контекста
        """
        try:
            # Поиск и скрейпинг статей
            articles = await web_search_service.search_and_scrape(query, max_results)
            
            # Формируем контекст из найденных статей
            context = {
                "web_sources": [],
                "summary": ""
            }
            
            for article in articles:
                context["web_sources"].append({
                    "title": article["title"],
                    "url": article["url"],
                    "content": article["content"][:1000]  # Ограничиваем длину для экономии токенов
                })
            
            # Формируем краткое описание найденных источников
            if context["web_sources"]:
                sources_summary = "\n".join([
                    f"- {source['title']} ({source['url']})"
                    for source in context["web_sources"]
                ])
                context["summary"] = f"Найдены следующие релевантные источники:\n{sources_summary}"
            
            return context
            
        except Exception as e:
            logger.error(f"Ошибка при сборе веб-информации: {str(e)}")
            return {"web_sources": [], "summary": "Не удалось собрать информацию из веб-источников"}

# Create singleton instance
coordinator_agent = CoordinatorAgent()