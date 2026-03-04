# core/rag/vectorstore.py
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import SentenceTransformerEmbeddings

class VectorStoreChroma:
    def __init__(self, persist_dir="chroma_db"):
        self.embeddings = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
        self.persist_dir = persist_dir
        self.vectordb = Chroma(persist_directory=persist_dir, embedding_function=self.embeddings)

    def build_index(self, documents, metadatas=None):
        """
        Add documents to Chroma. Optionally attach metadata.
        """
        self.vectordb.add_texts(documents, metadatas=metadatas)
        self.vectordb.persist()

    def search(self, query, top_k=5, course=None, difficulty=None):
        """
        Search Chroma with optional metadata filtering.
        Only one metadata filter key is allowed in Chroma, so we filter 'difficulty' in Python.
        """
        filter_param = None
        if course:
            filter_param = {"course": {"$eq": course}}  # only one filter key allowed

        results = self.vectordb.similarity_search(query, k=top_k, filter=filter_param)

        # Filter difficulty in Python
        if difficulty:
            results = [doc for doc in results if doc.metadata.get("difficulty") == difficulty]

        return results
