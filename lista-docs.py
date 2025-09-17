from opensearchpy import OpenSearch
import json
import warnings
from urllib3.exceptions import InsecureRequestWarning

# Suprimir warnings de SSL
warnings.simplefilter('ignore', InsecureRequestWarning)

# Conexión
es = OpenSearch(
    hosts=[{"host": "opensearch.madd.com.mx", "port": 9200}],
    http_auth=("admin", "GPSc0ntr0l1"),
    use_ssl=True,
    verify_certs=False
)

# Consulta (igual a tu GET)
search_query = {
    "size": 1000,
    "query": {"match_all": {}}
}

try:
    # Ejecutar búsqueda
    response = es.search(index="vacantefinal", body=search_query)
    hits = response["hits"]["hits"]
    print(f"Total de documentos encontrados: {len(hits)}")
    
    # Listar _id y nombre_de_la_vacante
    result = []
    for hit in hits:
        doc_id = hit["_id"]
        nombre = hit["_source"].get("nombre_de_la_vacante", "N/A")
        result.append({"_id": doc_id, "nombre_de_la_vacante": nombre})
    
    # Imprimir como JSON
    print("\nLista completa (JSON):")
    print(json.dumps(result, indent=2))
    
    # Imprimir como tabla simple
    print("\nTabla:")
    print("| # | _id                          | nombre_de_la_vacante                  |")
    print("|---|------------------------------|---------------------------------------|")
    for i, item in enumerate(result, 1):
        print(f"| {i} | {item['_id']:<28} | {item['nombre_de_la_vacante']:<39} |")
    
except Exception as e:
    print(f"Error: {str(e)}")
