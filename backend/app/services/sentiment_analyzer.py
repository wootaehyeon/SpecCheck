from typing import Dict, Tuple
import re

class SentimentAnalyzer:
    def __init__(self):
        self.positive_keywords = [
            '좋다', '좋음', '훌륭하다', '최고', '훌륭해', '탁월하다', '우수',
            '추천', '만족', '만족스럽다', '완벽', '완벽하다', '정말', '대단히',
            '매우', '굉장히', '정말', '매우', '굉장', '장점', '성능', '빠르다',
            '빠름', '효율', '가성비', '저렴', '싸다', '가격', '오버', '배치',
            '최신', '우수', '뛰어나다', '탁월', '훨씬', '낫다', '좋아',
            '괜찮다', '괜찮아', '쓸만', '꽤', '상당히', '정도로', '정도면'
        ]

        self.negative_keywords = [
            '나쁘다', '나쁨', '형편없다', '형편없어', '최악', '끔찍', '끔찍하다',
            '별로', '불만', '불만족', '실망', '실망스럽다', '문제', '문제가',
            '결함', '버그', '버그가', '느리다', '느림', '느려', '높다', '비싸다',
            '비쌈', '가격이', '비싸', '단점', '약점', '손상', '고장', '고장이',
            '끔찍', '지겨워', '지겨운', '하지만', '그런데', '그러나', '다만',
            '다만', '아쉽', '아쉽다', '아쉬워', '실패', '실패했', '실패한',
            '최악의', '안돼', '안됐', '안 돼', '엉망', '엉망이'
        ]

        self.neutral_keywords = [
            '보통', '중간', '괜찮', '그저', '그냥', '평범', '평범하', '무난',
            '무난한', '적절', '적절한', '해볼', '한번', '어쨌든', '아무튼',
            '한편', '이편', '저편', '이정도', '정도', '만큼', '만한', '돼',
            '됩니다', '됩니까', '입니다', '입니까', '이라고', '이라는'
        ]

    def analyze_sentiment(self, text: str) -> Tuple[str, float]:
        if not text:
            return "neutral", 0.5

        text_lower = text.lower()
        words = re.findall(r'[\w]+', text_lower)

        positive_count = sum(1 for word in words if word in self.positive_keywords)
        negative_count = sum(1 for word in words if word in self.negative_keywords)
        neutral_count = sum(1 for word in words if word in self.neutral_keywords)

        total_sentiment_words = positive_count + negative_count + neutral_count

        if total_sentiment_words == 0:
            return "neutral", 0.5

        positive_ratio = positive_count / total_sentiment_words
        negative_ratio = negative_count / total_sentiment_words

        if positive_count > negative_count and positive_count > neutral_count:
            score = 0.6 + (positive_ratio * 0.4)
            return "positive", min(1.0, score)
        elif negative_count > positive_count and negative_count > neutral_count:
            score = 0.4 - (negative_ratio * 0.4)
            return "negative", max(0.0, score)
        else:
            score = 0.5 + ((positive_count - negative_count) * 0.05)
            return "neutral", max(0.0, min(1.0, score))

    def analyze_crawl_results(self, results: list) -> list:
        analyzed_results = []
        for result in results:
            content = result.get('title', '') + ' ' + result.get('content', '')
            sentiment, score = self.analyze_sentiment(content)

            result_copy = result.copy()
            result_copy['sentiment'] = sentiment
            result_copy['sentiment_score'] = round(score, 2)
            analyzed_results.append(result_copy)

        return analyzed_results

    def get_sentiment_summary(self, results: list) -> Dict:
        if not results:
            return {
                'total': 0,
                'positive': 0,
                'negative': 0,
                'neutral': 0,
                'average_score': 0.5,
                'positive_ratio': 0.0,
                'negative_ratio': 0.0
            }

        positive_count = sum(1 for r in results if r.get('sentiment') == 'positive')
        negative_count = sum(1 for r in results if r.get('sentiment') == 'negative')
        neutral_count = len(results) - positive_count - negative_count

        average_score = sum(r.get('sentiment_score', 0.5) for r in results) / len(results)

        return {
            'total': len(results),
            'positive': positive_count,
            'negative': negative_count,
            'neutral': neutral_count,
            'average_score': round(average_score, 2),
            'positive_ratio': round(positive_count / len(results), 2),
            'negative_ratio': round(negative_count / len(results), 2)
        }
