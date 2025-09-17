import os
import json
from datetime import datetime
from flask import Flask, jsonify, render_template, request, abort, render_template_string  # NEW: fallback renderer
from opensearchpy import OpenSearch
from urllib3.exceptions import InsecureRequestWarning
import warnings
from dotenv import load_dotenv  # NEW

# Suppress SSL warnings for self-signed certs (matches existing usage)
warnings.simplefilter('ignore', InsecureRequestWarning)

# NEW: Load .env from this folder so os.getenv picks up values
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

INDEX_NAME = os.getenv("ES_INDEX", "vacantefinal")  # unchanged line but now reads from .env

def get_es_client():
    host = os.getenv("ES_HOST", "opensearch.madd.com.mx")
    port = int(os.getenv("ES_PORT", "9200"))
    user = os.getenv("ES_USER", "admin")
    password = os.getenv("ES_PASSWORD", "GPSc0ntr0l1")
    timeout = int(os.getenv("ES_TIMEOUT", "30"))

    return OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_auth=(user, password),
        use_ssl=True,
        verify_certs=False,
        ssl_show_warn=False,
        timeout=timeout,
    )

app = Flask(__name__, template_folder="templates")

@app.route("/")
def index():
    templates_dir = os.path.join(BASE_DIR, "templates")
    index_tpl = os.path.join(templates_dir, "index.html")
    if os.path.exists(index_tpl):
        return render_template("index.html", index_name=INDEX_NAME)  # pass index_name to template
    # Fallback minimal UI if templates are not created yet
    html = """
    <!doctype html>
    <html lang="es">
      <head>
        <meta charset="utf-8">
        <title>Vacantes Admin (fallback)</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
          .kv { font-family: monospace; font-size: 0.9rem; }
          .truncate { max-width: 360px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
          .modal-xl { --bs-modal-width: 95%; }
        </style>
      </head>
      <body class="p-3">
        <div class="container">
          <div class="d-flex align-items-center mb-3">
            <h3 class="me-3">Vacantes ({{ index_name }})</h3>
            <div class="ms-auto" style="max-width: 360px;">
              <input id="q" class="form-control" placeholder="Buscar por texto...">
            </div>
          </div>
          <div class="table-responsive">
            <table class="table table-sm table-striped align-middle" id="tbl">
              <thead class="table-light">
                <tr>
                  <th>_id</th>
                  <th>id_vacante</th>
                  <th>Vacante</th>
                  <th>Empresa</th>
                  <th>Creación</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody></tbody>
            </table>
          </div>
        </div>

        <!-- Edit Modal -->
        <div class="modal fade" id="editModal" tabindex="-1" aria-hidden="true">
          <div class="modal-dialog modal-dialog-scrollable modal-xl">
            <div class="modal-content">
              <div class="modal-header">
                <h5 class="modal-title">Editar documento</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
              </div>
              <div class="modal-body">
                <div id="docMeta" class="mb-3 text-secondary small"></div>
                <form id="editForm">
                  <div id="fieldsContainer" class="row g-3"></div>
                </form>
              </div>
              <div class="modal-footer">
                <div id="saveStatus" class="me-auto small text-muted"></div>
                <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancelar</button>
                <button id="saveBtn" type="button" class="btn btn-primary">Guardar cambios</button>
              </div>
            </div>
          </div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
          let currentDocId = null;
          const editModalEl = document.getElementById('editModal');
          const editModal = new bootstrap.Modal(editModalEl);
          const fieldsContainer = document.getElementById('fieldsContainer');
          const saveBtn = document.getElementById('saveBtn');
          const saveStatus = document.getElementById('saveStatus');
          const docMeta = document.getElementById('docMeta');

          function fmtDate(s){ try{const d=new Date(s); return isNaN(d)?(s||''):d.toLocaleString(); }catch(_){ return s||''; } }

          async function load(q){
            const url=new URL('/api/vacantes', window.location.origin);
            url.searchParams.set('limit','200'); if(q) url.searchParams.set('q', q);
            const r=await fetch(url);
            if(!r.ok){ throw new Error('No se pudo cargar la lista'); }
            const d=await r.json();
            const tb=document.querySelector('#tbl tbody'); tb.innerHTML='';
            (d.items||[]).forEach(it=>{
              const tr=document.createElement('tr');
              tr.innerHTML = `
                <td class="kv truncate" title="\${it._id||''}">\${it._id||''}</td>
                <td class="kv">\${it.id_vacante||''}</td>
                <td class="truncate" title="\${it.nombre_de_la_vacante||''}">\${it.nombre_de_la_vacante||''}</td>
                <td>\${it.empresa||''}</td>
                <td>\${fmtDate(it.fecha_creacion)}</td>
                <td><button class="btn btn-sm btn-primary btn-edit" data-id="\${it._id}">Editar</button></td>
              `;
              tb.appendChild(tr);
            });
          }

          async function openEdit(docId){
            currentDocId = docId;
            saveStatus.textContent = '';
            fieldsContainer.innerHTML = '';
            docMeta.textContent = 'Cargando...';

            const resp = await fetch(\`/api/vacantes/\${encodeURIComponent(docId)}\`);
            if(!resp.ok){ docMeta.textContent = 'Error al cargar el documento.'; return; }
            const data = await resp.json();
            docMeta.textContent = \`_id: \${data._id} | _index: \${data._index}\`;

            const src = data.source || {};
            const entries = Object.entries(src).sort(([a],[b])=>a.localeCompare(b));
            for (const [key, val] of entries) {
              const safeVal = (val === null || val === undefined) ? '' : String(val);
              const id = \`fld_\${key}\`;
              const isLong = safeVal.length > 80 || safeVal.includes('\\n');
              const col = document.createElement('div');
              col.className = 'col-12';
              col.innerHTML = isLong ? `
                <div class="form-floating">
                  <textarea class="form-control" id="\${id}" data-key="\${key}" style="height: 120px">\${safeVal}</textarea>
                  <label for="\${id}">\${key}</label>
                </div>
              ` : `
                <div class="form-floating">
                  <input type="text" class="form-control" id="\${id}" data-key="\${key}" value="\${safeVal}">
                  <label for="\${id}">\${key}</label>
                </div>
              `;
              fieldsContainer.appendChild(col);
            }
            editModal.show();
          }

          async function saveEdit(){
            if(!currentDocId) return;
            saveStatus.textContent = 'Guardando...';
            const inputs = fieldsContainer.querySelectorAll('[data-key]');
            const fields = {};
            inputs.forEach(inp => { fields[inp.getAttribute('data-key')] = inp.value; });
            const resp = await fetch(\`/api/vacantes/\${encodeURIComponent(currentDocId)}\`, {
              method: 'PATCH',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({ fields })
            });
            const res = await resp.json();
            if(resp.ok){
              saveStatus.textContent = 'Cambios guardados.';
              const q = document.getElementById('q').value.trim();
              await load(q);
              setTimeout(()=>editModal.hide(), 600);
            } else {
              saveStatus.textContent = \`Error: \${res.error || 'no se pudo guardar'}\`;
            }
          }

          document.addEventListener('click', (e)=>{
            const btn = e.target.closest('.btn-edit');
            if(btn){ openEdit(btn.getAttribute('data-id')); }
          });
          saveBtn.addEventListener('click', saveEdit);
          document.getElementById('q').addEventListener('input', e=>load(e.target.value.trim()));

          load('');
        </script>
      </body>
    </html>
    """
    return render_template_string(html, index_name=INDEX_NAME)

@app.get("/api/vacantes")
def list_vacantes():
    """
    Query params:
      - q: search text
      - offset: default 0
      - limit: default 50 (max 500)
    """
    try:
        q = request.args.get("q", "").strip()
        offset = int(request.args.get("offset", "0"))
        limit = min(int(request.args.get("limit", "50")), 500)

        es = get_es_client()
        query = {"match_all": {}} if not q else {
            "bool": {
                "should": [
                    {"wildcard": {"nombre_de_la_vacante.keyword": f"*{q}*"}},
                    {"wildcard": {"empresa.keyword": f"*{q}*"}},
                    {"wildcard": {"departamento.keyword": f"*{q}*"}},
                    {"wildcard": {"area.keyword": f"*{q}*"}},
                ]
            }
        }

        body = {
            "from": offset,
            "size": limit,
            "_source": [
                "id_vacante",
                "nombre_de_la_vacante",
                "empresa",
                "departamento",
                "area",
                "dias_para_atender_entrevistas",
                "horarios_disponibles_para_entrevistar",
                "fecha_creacion",
            ],
            "query": query,
            "sort": [{"fecha_creacion": {"order": "desc"}}]
        }

        resp = es.search(index=INDEX_NAME, body=body)
        total = resp.get("hits", {}).get("total", {}).get("value", 0)
        items = []
        for hit in resp.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            items.append({
                "_id": hit.get("_id"),
                "id_vacante": src.get("id_vacante"),
                "nombre_de_la_vacante": src.get("nombre_de_la_vacante"),
                "empresa": src.get("empresa"),
                "departamento": src.get("departamento"),
                "area": src.get("area"),
                "dias_para_atender_entrevistas": src.get("dias_para_atender_entrevistas"),
                "horarios_disponibles_para_entrevistar": src.get("horarios_disponibles_para_entrevistar"),
                "fecha_creacion": src.get("fecha_creacion"),
            })

        return jsonify({
            "total": total,
            "offset": offset,
            "limit": limit,
            "items": items
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/api/vacantes/<doc_id>")
def get_vacante(doc_id: str):
    try:
        es = get_es_client()
        res = es.get(index=INDEX_NAME, id=doc_id)
        src = res.get("_source", {})
        # Only return string-friendly fields by default; include all for power users
        return jsonify({
            "_id": res.get("_id"),
            "_index": res.get("_index"),
            "source": src
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 404

@app.patch("/api/vacantes/<doc_id>")
def patch_vacante(doc_id: str):
    """
    Body:
      {
        "fields": { "campo1": "valor", "campo2": "valor2", ... }
      }
    Applies OpenSearch partial update with {"doc": fields}.
    """
    try:
        payload = request.get_json(silent=True) or {}
        fields = payload.get("fields")
        if not isinstance(fields, dict) or not fields:
            return jsonify({"error": "Missing or invalid 'fields' payload"}), 400

        # Optional: sanitize non-string types minimally (leave as-is otherwise)
        # Example: ensure fecha_creacion is ISO if provided
        if "fecha_creacion" in fields and isinstance(fields["fecha_creacion"], datetime):
            fields["fecha_creacion"] = fields["fecha_creacion"].isoformat()

        es = get_es_client()
        es.update(index=INDEX_NAME, id=doc_id, body={"doc": fields})
        return jsonify({"status": "ok", "updated": list(fields.keys())})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/favicon.ico")
def favicon():
    return "", 204  # NEW: avoid 404s for favicon

def main():
    host = os.getenv("ADMIN_HOST", "0.0.0.0")
    port = int(os.getenv("ADMIN_PORT", "7020"))
    debug = os.getenv("ADMIN_DEBUG", "false").lower() == "true"
    print(f"Vacantes Admin running on http://{host}:{port} (index: {INDEX_NAME})")
    app.run(host=host, port=port, debug=debug)

if __name__ == "__main__":
    main()
