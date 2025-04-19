from flask import Flask, request, jsonify
from flask_cors import CORS
import jieba
import jieba.posseg as pseg
import torch
from transformers import BertTokenizer, BertForSequenceClassification
import numpy as np

app = Flask(__name__)
CORS(app)

# 加载预训练模型
MODEL_NAME = "uer/roberta-base-finetuned-jd-binary-chinese"  # 也可以使用其他中文情感模型
tokenizer = BertTokenizer.from_pretrained(MODEL_NAME)
model = BertForSequenceClassification.from_pretrained(MODEL_NAME)
model.eval()  # 设置为评估模式

# 加载预训练模型
# MODEL_CONFIG = {
#     "tokenizer_path": "d:/knowledge/repo/ai_chat/models/bert-base-chinese",
#     "model_path": "d:/knowledge/repo/ai_chat/models/bert_epoch_520.pth",
#     "device": torch.device("cuda" if torch.cuda.is_available() else "cpu")
# }
# # 初始化tokenizer和模型
# tokenizer = BertTokenizer.from_pretrained(MODEL_CONFIG["tokenizer_path"])
# model = Model().to(MODEL_CONFIG["device"])
# model.load_state_dict(torch.load(MODEL_CONFIG["model_path"]))
# model.eval()  # 设置为评估模式
# 情感词典保持不变
EMOTION_DICT = {
    "happy": {
        "words": [
            "开心", "快乐", "高兴", "欢喜", "愉快", "欢乐", "喜悦", "兴奋", 
            "棒", "好", "太好了", "不错", "很好", "优秀", "完美", "出色",
            "欢迎", "感谢", "谢谢", "很棒", "赞", "真棒", "厉害", "可以"
        ],
        "weight": 1.2  # 权重
    },
    "thinking": {
        "words": [
            "思考", "想想", "分析", "研究", "考虑", "推测", "猜测", "建议",
            "或许", "可能", "也许", "大概", "估计", "应该", "兴许", "没准",
            "让我", "稍等", "等一下", "容我", "让我想想", "我觉得", "我认为"
        ],
        "weight": 1.0
    },
    "elegant": {
        "words": [
            "优雅", "文雅", "高雅", "典雅", "雅致", "古风", "诗意", "从容",
            "请", "麻烦", "劳驾", "烦请", "如果方便", "不知可否", "恳请",
            "温柔", "细腻", "婉约", "清新", "脱俗", "高贵", "端庄"
        ],
        "weight": 0.8
    },
    "sad": {
        "words": [
            "抱歉", "对不起", "遗憾", "歉意", "不好意思", "很抱歉", "失礼",
            "无法", "不能", "没办法", "做不到", "恐怕不行", "难以", "不得不",
            "伤心", "难过", "悲伤", "惆怅", "忧郁", "沮丧", "失落"
        ],
        "weight": 1.1
    },
    "angry": {
        "words": [
            "生气", "愤怒", "不满", "恼火", "发火", "火大", "恼怒", "气愤",
            "警告", "严重", "严厉", "严肃", "必须", "一定要", "绝对", "坚决",
            "错误", "失败", "问题", "故障", "异常", "不行", "不可以", "不准"
        ],
        "weight": 1.3
    },
    "surprised": {
        "words": [
            "惊讶", "吃惊", "震惊", "意外", "没想到", "竟然", "居然", "原来",
            "哇", "啊", "真的吗", "难以置信", "不会吧", "天啊", "不是吧",
            "令人意外", "出乎意料", "让人惊讶", "奇怪", "不可思议"
        ],
        "weight": 0.9
    }
}

def get_bert_emotion(text):
    """使用BERT模型进行情感分析"""
    try:
        inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
        with torch.no_grad():
            outputs = model(**inputs)
            predictions = torch.nn.functional.softmax(outputs.logits, dim=1)
            
        # 获取情感概率
        positive_score = predictions[0][1].item()
        
        # 根据得分映射到不同情感
        if positive_score > 0.8:
            return "happy", positive_score
        elif positive_score > 0.6:
            return "elegant", positive_score
        elif positive_score < 0.2:
            return "angry", 1 - positive_score
        elif positive_score < 0.4:
            return "sad", 1 - positive_score
        else:
            return "thinking", 0.5
            
    except Exception as e:
        print(f"BERT分析错误: {str(e)}")
        return None, 0.0

def analyze_text_emotion(text):
    """结合规则和模型的情感分析"""
    # 使用规则方法
    words = pseg.cut(text)
    emotion_scores = {emotion: 0 for emotion in EMOTION_DICT.keys()}
    
    for word, flag in words:
        for emotion, config in EMOTION_DICT.items():
            if any(keyword in word or word in keyword for keyword in config["words"]):
                weight_multiplier = 1.0
                if flag.startswith('v'):
                    weight_multiplier = 1.2
                elif flag.startswith('a'):
                    weight_multiplier = 1.5
                elif flag.startswith('d'):
                    weight_multiplier = 1.3
                
                emotion_scores[emotion] += config["weight"] * weight_multiplier
    
    # 使用BERT模型
    bert_emotion, bert_confidence = get_bert_emotion(text)
    
    # 结合两种方法的结果
    if bert_emotion:
        # 如果BERT有高置信度的结果，增加对应情感的得分
        if bert_confidence > 0.7:
            emotion_scores[bert_emotion] += bert_confidence * 2
    
    # 获取最终情感
    max_score = max(emotion_scores.values())
    if max_score > 0:
        emotion = max(emotion_scores.items(), key=lambda x: x[1])[0]
        confidence = max_score / (sum(emotion_scores.values()) + 0.1)
    else:
        emotion = "default"
        confidence = 1.0
    
    # 输出详细分析结果
    print(f"Text: {text}")
    print(f"Rule-based scores: {emotion_scores}")
    print(f"BERT emotion: {bert_emotion} (confidence: {bert_confidence})")
    print(f"Final emotion: {emotion} (confidence: {confidence})")
    
    return emotion, confidence

@app.route('/analyze_emotion', methods=['POST'])
def analyze_emotion():
    try:
        data = request.get_json()
        text = data.get('text', '')
        
        emotion, confidence = analyze_text_emotion(text)
        
        response = {
            'emotion': emotion,
            'confidence': float(confidence),
            'text': text
        }
        
        print(f"Final analysis result: {response}")
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("正在加载模型和初始化服务...")
    app.run(port=5000, debug=False)  # 生产环境建议关闭debug模式