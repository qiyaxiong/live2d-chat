import sqlite3
import os
import numpy as np
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
import plotly.express as px
import pandas as pd
import json
import struct

# 检查数据库文件
db_path = "D:/knowledge/repo/ai_chat/edge-tts/memory_store/chroma.sqlite3"
if not os.path.exists(db_path):
    raise FileNotFoundError(f"数据库文件不存在: {db_path}")

# 连接数据库
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 获取向量数据
cursor.execute("SELECT id, vector, metadata FROM embeddings_queue WHERE vector IS NOT NULL")
rows = cursor.fetchall()

vectors = []
ids = []
texts = []
for row in rows:
    vector_id = row[0]
    vector_data = np.frombuffer(row[1], dtype=np.float32)
    metadata = json.loads(row[2]) if row[2] else {}
    
    vectors.append(vector_data)
    ids.append(vector_id)
    texts.append(metadata.get('chroma:document', ''))

# 转换为numpy数组
vectors_array = np.array(vectors)

# 使用KMeans进行聚类
n_clusters = 3  # 设置为3个聚类
kmeans = KMeans(n_clusters=n_clusters, random_state=42)
clusters = kmeans.fit_predict(vectors_array)

# 使用PCA降维到2D
pca = PCA(n_components=2)
vectors_2d = pca.fit_transform(vectors_array)

# 创建数据框
df = pd.DataFrame({
    'x': vectors_2d[:, 0],
    'y': vectors_2d[:, 1],
    'id': ids,
    'text': texts,
    'cluster': clusters
})

# 使用Plotly创建交互式散点图
fig = px.scatter(
    df, 
    x='x', 
    y='y',
    color='cluster',
    hover_data=['id', 'text'],
    color_discrete_sequence=['#FF6B6B', '#4ECDC4', '#45B7D1'],  # 设置三种颜色
    title='向量数据库语义聚类可视化 (PCA降维)',
    labels={
        'x': f'第一主成分 ({pca.explained_variance_ratio_[0]:.2%})',
        'y': f'第二主成分 ({pca.explained_variance_ratio_[1]:.2%})',
        'cluster': '语义聚类'
    }
)

# 更新图表布局
fig.update_layout(
    hoverlabel=dict(
        bgcolor="white",
        font_size=16,
        font_color="black"
    ),
    plot_bgcolor='rgba(240,240,240,0.2)',
    paper_bgcolor='rgba(255,255,255,1)',
    showlegend=True,
    legend_title_text='语义聚类'
)

# 设置颜色方案
fig.update_traces(
    marker=dict(
        size=8,
        opacity=0.7
    )
)

# 保存为HTML文件
fig.write_html("d:/knowledge/repo/ai_chat/vector_viz.html")