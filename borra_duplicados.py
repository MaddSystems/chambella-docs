from opensearchpy import OpenSearch
from collections import defaultdict
from datetime import datetime

# Conexión a OpenSearch con autenticación básica
es = OpenSearch(
    hosts=[{"host": "opensearch.madd.com.mx", "port": 9200}],
    http_auth=("admin", "GPSc0ntr0l1"),
    use_ssl=True,
    verify_certs=False  # ⚠️ pon True si tienes certificados válidos de CA
)

# Consulta para traer documentos
search_query = {
    "_source": ["fecha_creacion", "nombre_de_la_vacante"],
    "size": 1000,
    "query": {"match_all": {}}
}

# Ejecutar búsqueda
response = es.search(index="vacantefinal", body=search_query)
hits = response["hits"]["hits"]

# Agrupar por nombre_de_la_vacante
vacantes = defaultdict(list)
for hit in hits:
    doc_id = hit["_id"]
    nombre = hit["_source"]["nombre_de_la_vacante"]
    fecha = datetime.strptime(hit["_source"]["fecha_creacion"], "%Y-%m-%dT%H:%M:%S.%fZ")
    vacantes[nombre].append({"id": doc_id, "fecha": fecha})

# Identificar duplicados (conservar el más reciente)
ids_to_delete = []
for nombre, docs in vacantes.items():
    if len(docs) > 1:
        sorted_docs = sorted(docs, key=lambda x: x["fecha"])
        ids_to_delete.extend(doc["id"] for doc in sorted_docs[:-1])

# Borrar duplicados
for doc_id in ids_to_delete:
    es.delete(index="vacantefinal", id=doc_id)
    print(f"Deleted document with _id: {doc_id}")

print(f"Total documents deleted: {len(ids_to_delete)}")