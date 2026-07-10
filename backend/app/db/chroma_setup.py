import os
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from app.core.config import settings

def get_embeddings_model():
    try:
        return GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001", 
            google_api_key=settings.GEMINI_API_KEY
        )
    except Exception as e:
        print(f"⚠️ Embeddings initialization failed: {e}")
        return None

def initialize_knowledge_base():
    """Reads text files from the data folder and stores them in ChromaDB."""
    print("\n⏳ Initializing Vector Database from University Syllabus Notes...")
    documents = []
    
    if os.path.exists(settings.DATA_DIR):
        for filename in os.listdir(settings.DATA_DIR):
            if filename.endswith(".txt"):
                file_path = os.path.join(settings.DATA_DIR, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                    documents.append(Document(page_content=text, metadata={"source": filename}))
    
    if not documents:
        print("⚠️ No syllabus documents found in the 'data' folder.")
        return None

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = text_splitter.split_documents(documents)
    embeddings = get_embeddings_model()

    if embeddings:
        vectorstore = Chroma.from_documents(documents=chunks, embedding=embeddings, persist_directory=settings.CHROMA_DB_DIR)
        print("✅ Vector Database (ChromaDB) Initialized Successfully!\n")
        return vectorstore
    return None

def get_vectorstore():
    """Returns the existing ChromaDB or creates a new one if it doesn't exist."""
    embeddings = get_embeddings_model()
    if os.path.exists(settings.CHROMA_DB_DIR) and os.listdir(settings.CHROMA_DB_DIR):
        return Chroma(persist_directory=settings.CHROMA_DB_DIR, embedding_function=embeddings)
    else:
        return initialize_knowledge_base()