from opensearchpy import OpenSearch
import warnings
from urllib3.exceptions import InsecureRequestWarning

# Suprimir warnings de SSL (opcional, pero limpia la salida)
warnings.simplefilter('ignore', InsecureRequestWarning)

# Conexión a OpenSearch con autenticación básica (igual que en tu referencia)
es = OpenSearch(
    hosts=[{"host": "opensearch.madd.com.mx", "port": 9200}],
    http_auth=("admin", "GPSc0ntr0l1"),
    use_ssl=True,
    verify_certs=False  # ⚠️ pon True si tienes certificados válidos de CA
)

# Config
index = "vacantefinal"
doc_id = "Ib-EHZkB1zY9OhrrPxuY"

try:
    # Leer doc
    doc = es.get(index=index, id=doc_id)['_source']
    print(f"Documento leído: {doc.get('nombre_de_la_vacante', 'Sin nombre')}")

    # Agregar campos
    doc['viaticos'] = "No aplica. Es un puesto de oficina."
    doc['uniforme'] = "Si, la empresa les da uniforme."
    doc['base_casa'] = "No aplica. Es un puesto de oficina."
    doc['seguro_social'] = "Si, contamos con seguro social desde tu primer dia de trabajo."

    # Actualizar (mergea los cambios sin sobrescribir todo el doc)
    es.update(index=index, id=doc_id, body={"doc": doc})
    print("Doc actualizado exitosamente.")

except Exception as e:
    print(f"Error: {str(e)}")
    # Si no existe el doc, puedes crearlo con index
    # es.index(index=index, id=doc_id, body=doc)  # Descomenta si necesitas crear