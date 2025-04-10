    async def analyze_document_image(self, image_url: str) -> Dict[str, Any]:
        """
        Анализирует изображение юридического документа и потоково возвращает результаты
        """
        prompt = """
        Проанализируй детально этот юридический документ и выдели следующую информацию:
        
        1. Тип документа (договор, судебное решение, заявление и т.д.)
        2. Основные стороны и их реквизиты (ФИО, организации, адреса, реквизиты)
        3. Ключевые положения и обязательства сторон
        4. Даты, сроки и временные рамки действия документа
        5. Юридически значимые детали (условия, размеры платежей, санкции)
        6. Основания возникновения правоотношений
        7. Применимое законодательство и нормативно-правовые акты
        
        Предоставь структурированный ответ на русском языке с чётким разделением на разделы.
        Если какая-то информация отсутствует или нечитаема, укажи это.
        """
        
        # Проверяем, является ли image_url локальным файлом
        if os.path.isfile(image_url):
            try:
                with open(image_url, "rb") as img_file:
                    base64_image = base64.b64encode(img_file.read()).decode('utf-8')
                    image_url = f"data:image/jpeg;base64,{base64_image}"
                    logger.info(f"Локальный файл конвертирован в base64")
            except Exception as e:
                logger.error(f"Ошибка при чтении локального файла: {str(e)}")
                return {
                    "error": f"Не удалось прочитать файл: {str(e)}",
                    "success": False
                }
        
        # Вызов API с передачей изображения
        result = await call_qwen_api(
            prompt=prompt,
            image_url=image_url,
            max_tokens=4000,
            temperature=0.3
        )
        
        if result["success"]:
            document_type = self._determine_document_type(result["text"])
            
            # Добавляем типизированные подсказки для дальнейшего анализа
            follow_up_tips = self._generate_follow_up_tips(document_type)
            
            # Проверяем, содержит ли документ таблицы
            has_tables = self._check_for_tables(result["text"])
            
            # Если это документ со сложной структурой, предлагаем дополнительный анализ
            complex_document = document_type in ["contract", "court_decision", "statute"]
            
            analysis_result = {
                "document_analysis": result["text"],
                "document_type": document_type,
                "document_type_readable": self._get_readable_document_type(document_type),
                "follow_up_tips": follow_up_tips,
                "has_tables": has_tables,
                "is_complex": complex_document,
                "success": True
            }
            
            # Извлекаем структурированные данные из анализа
            structured_data = self._extract_structured_data(result["text"], document_type)
            if structured_data:
                analysis_result["structured_data"] = structured_data
            
            # Сохраняем результат анализа в Elasticsearch
            try:
                await self._save_analysis_to_elasticsearch(analysis_result)
            except Exception as e:
                logger.error(f"Ошибка при сохранении анализа в Elasticsearch: {str(e)}")
            
            return analysis_result
        else:
            error_msg = result.get('error', 'Неизвестная ошибка')
            logger.error(f"Ошибка анализа документа: {error_msg}")
            return {
                "error": f"Не удалось проанализировать документ: {error_msg}",
                "success": False
            }
    

    def _extract_structured_data(self, analysis_text: str, document_type: str) -> Optional[Dict[str, Any]]:
        """
        Извлекает структурированные данные из текста анализа в зависимости от типа документа
        """
        structured_data = {}
        
        # Извлекаем даты из текста
        dates = re.findall(r'(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})', analysis_text)
        if dates:
            structured_data["dates"] = dates
        
        # Извлекаем суммы денег
        money_amounts = re.findall(r'(\d+(?:[\s,\.]\d+)*(?:\s?(?:руб(?:лей)?|₽|RUB|USD|\$|EUR|€)))', analysis_text)
        if money_amounts:
            structured_data["money_amounts"] = money_amounts
        
        # Извлекаем ФИО
        names = re.findall(r'([А-Я][а-я]+\s+[А-Я][а-я]+(?:\s+[А-Я][а-я]+)?)', analysis_text)
        if names:
            structured_data["names"] = names
        
        # Извлекаем данные в зависимости от типа документа
        if document_type == "contract":
            # Извлекаем стороны договора
            parties = []
            party_sections = re.findall(r'Сторона\s+\d+[:\s]+(.*?)(?=Сторона\s+\d+|$)', analysis_text, re.DOTALL)
            for party in party_sections:
                parties.append(party.strip())
            
            if parties:
                structured_data["parties"] = parties
                
            # Попытка найти предмет договора
            subject_match = re.search(r'Предмет(?:\s+договора)?[:\s]+(.*?)(?=\n\n|\n[А-Я]|$)', analysis_text, re.DOTALL)
            if subject_match:
                structured_data["subject"] = subject_match.group(1).strip()
                
        elif document_type == "court_decision":
            # Извлекаем информацию о суде
            court_match = re.search(r'(?:суд|СУД)[:\s]+(.*?)(?=\n\n|\n[А-Я]|$)', analysis_text, re.DOTALL)
            if court_match:
                structured_data["court"] = court_match.group(1).strip()
                
            # Номер дела
            case_number_match = re.search(r'(?:дело|номер дела|№)[:\s]+([A-Яа-я0-9№\-/]+)', analysis_text)
            if case_number_match:
                structured_data["case_number"] = case_number_match.group(1).strip()
                
            # Истец и ответчик
            plaintiff_match = re.search(r'(?:истец|ИСТЕЦ)[:\s]+(.*?)(?=\n\n|\n[А-Я]|ответчик|ОТВЕТЧИК|$)', analysis_text, re.DOTALL)
            if plaintiff_match:
                structured_data["plaintiff"] = plaintiff_match.group(1).strip()
                
            defendant_match = re.search(r'(?:ответчик|ОТВЕТЧИК)[:\s]+(.*?)(?=\n\n|\n[А-Я]|$)', analysis_text, re.DOTALL)
            if defendant_match:
                structured_data["defendant"] = defendant_match.group(1).strip()
                
        elif document_type == "legal_statement":
            # Кому адресовано
            addressee_match = re.search(r'(?:кому|в|директору|руководителю)[:\s]+(.*?)(?=\n\n|\nот\s|$)', analysis_text, re.DOTALL)
            if addressee_match:
                structured_data["addressee"] = addressee_match.group(1).strip()
                
            # От кого
            from_match = re.search(r'(?:от|заявитель)[:\s]+(.*?)(?=\n\n|\n[А-Я]|$)', analysis_text, re.DOTALL)
            if from_match:
                structured_data["from"] = from_match.group(1).strip()
        
        return structured_data if structured_data else None

    def _check_for_tables(self, text: str) -> bool:
        """
        Проверяет наличие таблиц в тексте
        """
        # Простая эвристика для определения таблиц - много пробелов или символов табуляции в строке
        lines = text.split('\n')
        for line in lines:
            if line.count('  ') > 3 or line.count('\t') > 1:
                return True
                
        # Также ищем маркеры, которые часто используются в описании таблиц
        table_markers = ['таблица', 'табл.', 'столбец', 'строка', 'графа', 'ячейка']
        for marker in table_markers:
            if marker in text.lower():
                return True
        
        return False


    async def _save_analysis_to_elasticsearch(self, analysis_result: Dict[str, Any]) -> None:
        """
        Сохраняет результат анализа документа в Elasticsearch
        
        Аргументы:
        analysis_result -- словарь с результатами анализа
        """
        try:
            document_data = {
                "content": analysis_result["document_analysis"],
                "document_type": analysis_result["document_type"],
                "document_type_readable": analysis_result["document_type_readable"],
                "analysis_date": "now",
                "source": "document_analysis",
                "metadata": {
                    "follow_up_tips": analysis_result["follow_up_tips"]
                }
            }
            
            # Используем ElasticsearchService для сохранения документа
            await self.es_service.index_document(
                index="document_analysis",
                document=document_data
            )
            
            logger.info("Результат анализа успешно сохранен в Elasticsearch")
        except Exception as e:
            logger.error(f"Ошибка при сохранении в Elasticsearch: {str(e)}")
            raise
    
    def _determine_document_type(self, text: str) -> str:
        """
        Определяет тип документа на основе анализа содержания
        
        Аргументы:
        text -- текст анализа документа
        
        Возвращает:
        Строковый код типа документа
        """
        if not text:
            return "unknown"
        
        text = text.lower()
        scores = {}
        
        # Подсчитываем "очки" для каждого типа документа
        for doc_type, keywords in self.document_types.items():
            score = 0
            for keyword in keywords:
                if keyword in text:
                    score += 1
            scores[doc_type] = score
        
        # Находим тип с максимальным количеством совпадений
        if not scores:
            return "unknown"
        
        max_score = max(scores.values())
        if max_score == 0:
            return "other_legal_document"
        
        # Если есть несколько типов с одинаковым количеством совпадений, выбираем первый
        for doc_type, score in scores.items():
            if score == max_score:
                return doc_type
        
        return "other_legal_document"
    
    def _get_readable_document_type(self, doc_type: str) -> str:
        """
        Возвращает читаемое название типа документа на русском
        """
        readable_types = {
            "contract": "Договор",
            "lawsuit": "Исковое заявление",
            "court_decision": "Судебное решение",
            "appeal": "Апелляционная жалоба",
            "power_of_attorney": "Доверенность",
            "statute": "Устав",
            "legal_statement": "Ходатайство",
            "notary_document": "Нотариальный документ",
            "official_letter": "Официальное письмо",
            "other_legal_document": "Иной юридический документ",
            "unknown": "Неопределенный тип документа"
        }
        return readable_types.get(doc_type, "Неопределенный тип документа")
    
    def _generate_follow_up_tips(self, doc_type: str) -> List[str]:
        """
        Генерирует подсказки для дальнейших действий в зависимости от типа документа
        """
        tips = {
            "contract": [
                "Проверьте сроки исполнения обязательств",
                "Обратите внимание на условия расторжения договора",
                "Проверьте ответственность сторон за нарушение обязательств"
            ],
            "lawsuit": [
                "Проверьте соблюдение процессуальных сроков",
                "Обратите внимание на обоснованность исковых требований",
                "Рассмотрите возможность мирового соглашения"
            ],
            "court_decision": [
                "Проверьте сроки обжалования решения",
                "Изучите мотивировочную часть решения",
                "Определите порядок исполнения решения"
            ],
            "appeal": [
                "Проверьте соблюдение сроков подачи жалобы",
                "Изучите обоснованность доводов жалобы",
                "Рассмотрите необходимость предоставления дополнительных доказательств"
            ],
            "power_of_attorney": [
                "Проверьте срок действия доверенности",
                "Уточните объем полномочий представителя",
                "Проверьте наличие права передоверия"
            ]
        }
        
        # Возвращаем подсказки для данного типа документа или общие подсказки
        return tips.get(doc_type, [
            "Проверьте правильность оформления документа",
            "Обратите внимание на сроки и даты в документе",
            "Изучите права и обязанности сторон"
        ])
    
    async def advanced_document_analysis(self, image_url: str, specific_question: str = None) -> Dict[str, Any]:
        """
        Проводит углубленный анализ документа с возможностью задать конкретный вопрос
        
        Аргументы:
        image_url -- URL изображения или путь к локальному файлу
        specific_question -- конкретный вопрос по документу (опционально)
        
        Возвращает:
        Словарь с результатами углубленного анализа
        """
        # Сначала получаем базовый анализ
        base_analysis = await self.analyze_document_image(image_url)
        
        if not base_analysis.get("success", False):
            return base_analysis
        
        # Если указан конкретный вопрос, запрашиваем дополнительный анализ
        if specific_question:
            prompt = f"""
            Вам представлен анализ юридического документа:
            
            {base_analysis['document_analysis']}
            
            Пожалуйста, ответьте на следующий конкретный вопрос о документе:
            {specific_question}
            
            Дайте детальный ответ на основе информации из документа. Если в документе недостаточно данных для ответа, 
            укажите это и предложите, какую дополнительную информацию нужно запросить.
            """
            
            specific_result = await call_qwen_api(
                prompt=prompt,
                max_tokens=1500,
                temperature=0.3
            )
            
            if specific_result["success"]:
                base_analysis["specific_analysis"] = specific_result["text"]
            else:
                base_analysis["specific_analysis_error"] = specific_result.get("error", "Не удалось выполнить анализ по конкретному вопросу")
        
        return base_analysis
    
    async def process_query(self, query_data: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Обрабатывает запрос с изображением и опционально текстом
        
        Аргументы:
        query_data -- URL изображения или словарь с параметрами {image_url, question}
        
        Возвращает:
        Результат анализа документа
        """
        try:
            # Проверяем тип входных данных
            if isinstance(query_data, str):
                # Если передана только строка, считаем её URL изображения
                return await self.analyze_document_image(query_data)
            elif isinstance(query_data, dict) and 'image_url' in query_data:
                # Если передан словарь с параметрами
                image_url = query_data['image_url']
                specific_question = query_data.get('question')
                
                if specific_question:
                    # Если есть конкретный вопрос, делаем расширенный анализ
                    return await self.advanced_document_analysis(image_url, specific_question)
                else:
                    # Иначе делаем обычный анализ
                    return await self.analyze_document_image(image_url)
            else:
                return {
                    "error": "Неверный формат запроса. Ожидается URL изображения или словарь с параметрами",
                    "success": False
                }
                
        except Exception as e:
            logger.error(f"Ошибка обработки запроса в агенте анализа документов: {str(e)}")
            return {"error": str(e), "success": False}

# Создание экземпляра-синглтона
document_analysis_agent = DocumentAnalysisAgent()
