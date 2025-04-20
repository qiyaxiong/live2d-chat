from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
import chromadb
from chromadb.utils import embedding_functions
import uvicorn
from datetime import datetime, timedelta

class Config:
    EMBEDDING_MODEL = "all-MiniLM-L6-v2"

class Memory(BaseModel):
    user_message: str
    assistant_response: str
    timestamp: Optional[str] = None
    metadata: Optional[Dict] = None

class Query(BaseModel):
    query: str
    limit: int = 3

# 初始化ChromaDB
client = chromadb.PersistentClient(path="./memory_store")

# 使用sentence-transformers进行向量嵌入
embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=Config.EMBEDDING_MODEL
)

# 获取或创建集合
collection = client.get_or_create_collection(
    name="chat_memories",
    metadata={"hnsw:space": "cosine"},
    embedding_function=embedding_function
)

app = FastAPI()

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def cleanup_old_memories():
    """清理过期的记忆"""
    try:
        # 获取所有记忆
        all_memories = collection.get()
        if not all_memories or not all_memories["metadatas"]:
            return
        
        # 计算截止时间
        cutoff_time = datetime.now() - timedelta(days=Config.MEMORY_RETENTION_DAYS)
        
        # 找出需要删除的记忆ID
        ids_to_delete = []
        for idx, metadata in enumerate(all_memories["metadatas"]):
            memory_time = datetime.fromisoformat(metadata["timestamp"])
            if memory_time < cutoff_time:
                ids_to_delete.append(all_memories["ids"][idx])
        
        # 批量删除过期记忆
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            print(f"Cleaned up {len(ids_to_delete)} old memories")
    except Exception as e:
        print(f"Error during cleanup: {str(e)}")

@app.post("/save_memory")
async def save_memory(memory: Memory):
    try:
        # 组合用户消息和助手回复
        combined_text = f"User: {memory.user_message}\nAssistant: {memory.assistant_response}"

        # 生成新的 memory_id，包含时间戳以便于排序
        current_time = datetime.now()
        memory_id = f"memory_{current_time.strftime('%Y%m%d_%H%M%S')}"

        # 准备元数据
        metadata = {
            "timestamp": current_time.isoformat(),
            "user_message": memory.user_message,
            "assistant_response": memory.assistant_response
        }
        if memory.metadata:
            metadata.update(memory.metadata)

        # 存储新的记忆
        collection.add(
            documents=[combined_text],
            ids=[memory_id],
            metadatas=[metadata]
        )

        return {"status": "saved", "memory_id": memory_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/retrieve_memories")
async def retrieve_memories(query: Query):
    try:
        # 从ChromaDB检索相关记忆
        results = collection.query(
            query_texts=[query.query],
            n_results=query.limit,
            include=["documents", "metadatas", "distances"]
        )
        
        # 处理结果
        memories = []
        if results and results['documents']:
            for doc, metadata, distance in zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            ):
                # 计算记忆时间
                memory_time = datetime.fromisoformat(metadata["timestamp"])
                time_ago = datetime.now() - memory_time
                
                # 将距离转换为相似度分数
                similarity_score = 1 - (distance / 2)
                
                memories.append({
                    "text": doc,
                    "timestamp": metadata["timestamp"],
                    "time_ago": str(time_ago).split('.')[0],  # 格式化时间差
                    "similarity_score": float(similarity_score)
                })
        
        return {"memories": memories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    try:
        all_memories = collection.get()
        memory_count = len(all_memories["ids"]) if all_memories else 0
                # 检查知识库服务
        import requests
        try:
            kb_response = requests.get("http://localhost:3001/api/status", timeout=2)
            kb_status = "healthy" if kb_response.status_code == 200 else "unhealthy"
        except:
            kb_status = "unavailable"
        # 获取最早和最新的记忆时间
        oldest_time = None
        newest_time = None
        if memory_count > 0:
            timestamps = [datetime.fromisoformat(m["timestamp"]) for m in all_memories["metadatas"]]
            oldest_time = min(timestamps).isoformat()
            newest_time = max(timestamps).isoformat()
        
        return {
            "status": "healthy",
            "memory_count": memory_count,
            "oldest_memory": oldest_time,
            "newest_memory": newest_time,
            "retention_days": Config.MEMORY_RETENTION_DAYS
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

@app.post("/cleanup")
async def force_cleanup():
    """手动触发清理"""
    try:
        cleanup_old_memories()
        return {"status": "cleanup completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("memory_service:app", host="0.0.0.0", port=5090, reload=True)