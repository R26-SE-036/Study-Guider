
from app.db.chroma_setup import get_vectorstore

def retrieve_context(query: str, k=2):
    """Searches the Vector DB for notes related to the student's error"""
    try:
        vectorstore = get_vectorstore()
        if not vectorstore:
            return "No specific university guidelines available."
        
        # Retrieve the top 'k' most relevant chunks
        retriever = vectorstore.as_retriever(search_kwargs={"k": k})
        docs = retriever.invoke(query)
        
        context = "\n".join([doc.page_content for doc in docs])
        return context
    except Exception as e:
        print(f"⚠️ Retrieval Error: {e}")
        return "No specific university guidelines available."
