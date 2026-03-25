from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    model_name="gpt2", chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
)


def split_text(text: str) -> list[str]:
    return splitter.split_text(text)
