const axios = require('axios');
require('dotenv').config();

class AIService {
  constructor() {
    this.apiKey = process.env.QWEN_API_KEY;
    this.endpoint = process.env.QWEN_API_ENDPOINT;
  }

  async generateResponse(text) {
    try {
      const response = await axios.post(
        this.endpoint,
        {
          model: "qwen-plus",
          input: {
            messages: [
              {
                role: "user",
                content: text
              }
            ]
          }
        },
        {
          headers: {
            'Authorization': `Bearer ${this.apiKey}`,
            'Content-Type': 'application/json'
          }
        }
      );
      return response.data;
    } catch (error) {
      console.error('AI 服务调用失败:', error);
      return null;
    }
  }
}

module.exports = new AIService();