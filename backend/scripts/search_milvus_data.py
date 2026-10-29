from pymilvus import MilvusClient

client = MilvusClient(
    uri="http://localhost:19530"
)

# client.query(
#     collection_name="agent_chat_memories",
#     filter="id like '%'",
#     output_fields=["*"]
# )
#
# client.search(
#     collection_name="agent_chat_memories",
#     data=[embedding],
#     limit=3,
#     output_fields=["text", "metadata"]
# )
res = client.query(
    collection_name="agent_chat_memories",
    filter="id != ''",
    output_fields=[
        "id",
        "text",
        "metadata",
    ],
)

for item in res:
    print(item)