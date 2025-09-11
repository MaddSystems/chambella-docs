import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import logging
import os
import sys
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Union
from mcp.server.fastmcp import FastMCP, Context
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.responses import StreamingResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import json
import time
from decimal import Decimal
import datetime
import re
import calendar

# Global variable for Id_Puesto field name (internal use)
ID_PUESTO = "id_vacante"

# Global variable for interview days field name (internal use)
DIAS_ENTREVISTA = "dias_para_atender_entrevistas"

# Global variable for interview times field name (internal use)
HORARIOS_ENTREVISTA = "horarios_disponibles_para_entrevistar"

# Global variables for other standardized field names (internal use)
PUESTO = "nombre_de_la_vacante"
NOMBRE_VACANTE = "nombre_de_vacante"
EMPRESA = "empresa"
DEPARTAMENTO = "departamento"
AREA = "area"

# Field mapping for backward compatibility (new_name -> old_name for API responses)
FIELD_MAPPING_RESPONSE = {
    "id_vacante": "Id_Vacante",
    "nombre_de_la_vacante": "Nombre_de_la_vacante",
    "empresa": "Empresa",
    "departamento": "Departamento",
    "area": "Area",
    "dias_para_atender_entrevistas": "Dias_para_atender_Entrevistas",
    "horarios_disponibles_para_entrevistar": "Horarios_disponibles_para_Entrevistar",
}

# Field mapping for querying (old_name -> new_name for internal queries)
FIELD_MAPPING_QUERY = {
    "Id_Vacante": "id_vacante",
    "Nombre_de_la_vacante": "nombre_de_la_vacante",
    "Empresa": "empresa",
    "Departamento": "departamento",
    "Area": "area",
    "Dias_para_atender_Entrevistas": "dias_para_atender_entrevistas",
    "Horarios_disponibles_para_Entrevistar": "horarios_disponibles_para_entrevistar",
}

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("mcp-elasticsearch-server")

# Import OpenSearch - will raise ImportError if not available
try:
    from opensearchpy import OpenSearch
    logger.info("Successfully imported OpenSearch module")
except ImportError:
    logger.critical("OpenSearch module not found! Please install it with: pip install opensearch-py")
    raise ImportError("OpenSearch module is required but not installed. Run: pip install opensearch-py")

# OpenSearch configuration from environment variables
ES_CONFIG = {
    "hosts": [{"host": "opensearch.madd.com.mx", "port": 9200}],
    "http_auth": (
        os.getenv("ES_USER", "admin"),
        os.getenv("ES_PASSWORD", "GPSc0ntr0l1")
    ),
    "use_ssl": True,
    "verify_certs": False,
    "ssl_show_warn": False,
    "timeout": int(os.getenv("ES_TIMEOUT", "30"))
}

# Custom JSON encoder to handle special types
class EsJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, datetime.date):
            return obj.isoformat()
        elif isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return super().default(obj)

# Application context for lifecycle management
@dataclass
class AppContext:
    es_client: OpenSearch

# Lifecycle management for OpenSearch connection
@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage OpenSearch connection lifecycle."""
    logger.info("Starting MCP OpenSearch server lifecycle")
    try:
        start_time = time.time()
        # Create OpenSearch client with updated configuration
        es_client = OpenSearch(**ES_CONFIG)
        
        # Check connection using info()
        try:
            info = es_client.info()
            es_version = info.get("version", {}).get("number", "unknown")
            logger.info(f"Connected to OpenSearch version {es_version}")
        except Exception as e:
            logger.error(f"Failed to get OpenSearch info: {e}")
            raise ConnectionError(f"Could not connect to OpenSearch: {e}")
            
        logger.info(f"OpenSearch connection established in {time.time() - start_time:.2f} seconds")
        yield AppContext(es_client=es_client)
    except Exception as e:
        logger.error(f"Failed to connect to OpenSearch: {e}")
        raise
    finally:
        if 'es_client' in locals():
            es_client.close()
            logger.info("OpenSearch connection closed")

# Initialize MCP server
mcp = FastMCP(
    name="Elasticsearch MCP Server",
    lifespan=app_lifespan,
    dependencies=["elasticsearch"]
)

# Middleware to log requests and responses
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.debug(f"Request: {request.method} {request.url} Headers: {request.headers}")
        try:
            response = await call_next(request)
            logger.debug(f"Response: Status {response.status_code}")
            return response
        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            raise

# Resource: OpenSearch indices info
@mcp.resource("schema://main")
def get_schema() -> str:
    """Provide the OpenSearch indices info as a resource."""
    try:
        es = OpenSearch(**ES_CONFIG)
        indices = es.indices.get("*")
        schema_info = []
        
        for index_name, index_info in indices.items():
            mappings = index_info.get("mappings", {}).get("properties", {})
            for field_name, field_info in mappings.items():
                field_type = field_info.get("type", "unknown")
                schema_info.append(f"Index: {index_name}, Field: {field_name}, Type: {field_type}")
        
        es.close()
        return "\n".join(schema_info)
    except Exception as e:
        logger.error(f"Error fetching schema: {e}")
        return f"Error: {str(e)}"


@mcp.tool()
def search_by_ad_id(ad_id: str, ctx: Context, detail_level: str = "summary") -> str:
    """
    Search for a vacancy by ad_id and return its associated nombre_de_la_vacante.
    """
    logger.debug(f"Searching by ad_id: {ad_id}, detail_level: {detail_level}")
    try:
        es = ctx.request_context.lifespan_context.es_client
        
        query = {
            "query": {
                "match": {
                    "ad_id": ad_id
                }
            }
        }
        
        response = es.search(
            #index="vacantes",
            index="vacantefinal",
            body=query
        )
        
        if response["hits"]["total"]["value"] == 0:
            return json.dumps({"error": "No vacancy found with this ad_id"})
        
        vacancy = response["hits"]["hits"][0]["_source"]
        vacancy["_id"] = response["hits"]["hits"][0]["_id"]
        vacancy["_index"] = response["hits"]["hits"][0]["_index"]
        
        formatted_result = format_document(vacancy, detail_level)
        logger.info(vacancy)
        logger.info(detail_level)
        logger.info(f"Found vacancy with ad_id {ad_id}, id_vacante: {formatted_result.get(ID_PUESTO, 'N/A')}")
        logger.info(formatted_result)
        return json.dumps(formatted_result, cls=EsJSONEncoder)
        
    except Exception as e:
        error_msg = f"Error searching by ad_id: {str(e)}"
        logger.error(error_msg)
        return json.dumps({"error": error_msg})

# Function to check if a job/vacancy is still available
def is_vacancy_available(doc: Dict[str, Any]) -> bool:
    """
    Check if a vacancy is still available based on document fields.
    """
    # Check for explicit unavailability indicators
    if doc.get("Estatus") == "Cerrada":
        return False
    if doc.get("Estado") == "Cancelada":
        return False
    
    # Check quantity of vacancies
    cantidad = doc.get("Cantidad_de_vacantes")
    if cantidad and cantidad == "0":
        return False
        
    # Check expiration date if available
    if "fecha_expiracion" in doc:
        try:
            expiration_date = doc.get("fecha_expiracion")
            if expiration_date:
                # Convert to datetime if it's a string
                if isinstance(expiration_date, str):
                    expiration_date = datetime.datetime.fromisoformat(expiration_date.replace("Z", "+00:00"))
                
                # Compare with current date
                if expiration_date < datetime.datetime.now(datetime.timezone.utc):
                    return False
        except Exception as e:
            logger.warning(f"Error checking expiration date: {e}")
    
    # Default to available if no negative indicators found
    return True

# Format document for display
def format_document(doc: Dict[str, Any], detail_level: str = "summary") -> Dict[str, Any]:
    """
    Format a document for display with appropriate level of detail.
    Maps internal new field names back to old field names for backward compatibility.
    """
    result = {}
    
    # Basic fields to include (using internal field names first)
    basic_fields = [
        ID_PUESTO, PUESTO, NOMBRE_VACANTE, 
        EMPRESA, DEPARTAMENTO, AREA
    ]
    
    # Check for both old and new field names and map to old names for response
    for field in basic_fields:
        if field in doc:
            # Map new field name back to old field name for response
            old_field_name = FIELD_MAPPING_RESPONSE.get(field, field)
            result[old_field_name] = doc[field]
        else:
            # Check if any old field name maps to this new field
            for old_field, new_field in FIELD_MAPPING_QUERY.items():
                if new_field == field and old_field in doc:
                    result[old_field] = doc[old_field]
                    break
    
    # Include ID and source index
    if "_id" in doc:
        result["_id"] = doc["_id"]
    if "_index" in doc:
        result["_index"] = doc["_index"]
    
    # Interview scheduling fields - check both old and new names
    interview_fields = [
        DIAS_ENTREVISTA,
        HORARIOS_ENTREVISTA,
        "Tiempo_maximo_de_contratacion"
    ]
    
    # Always include interview scheduling fields if available
    for field in interview_fields:
        if field in doc and doc[field] and doc[field] != "-":
            # Map new field name back to old field name for response
            old_field_name = FIELD_MAPPING_RESPONSE.get(field, field)
            result[old_field_name] = doc[field]
        else:
            # Check for old field name
            for old_field, new_field in FIELD_MAPPING_QUERY.items():
                if new_field == field and old_field in doc and doc[old_field] and doc[old_field] != "-":
                    result[old_field] = doc[old_field]
                    break
    
    # For summary view, include just key fields
    if detail_level == "summary":
        summary_fields = [
            "Objetivo_del_puesto", "Sueldo_Neto_Min", "Sueldo_Max", 
            "Lugar", "Oficinas", "Tipo_de_contratacion", "Jornada_Laboral"
        ]
        
        for field in summary_fields:
            if field in doc and doc[field] and doc[field] != "-":
                result[field] = doc[field]
                
        # Add availability status
        result["disponible"] = is_vacancy_available(doc)
        
    # For detailed view, include all fields except internal or irrelevant ones
    elif detail_level == "detail":
        exclude_fields = [
            "_id", "_index", "_score", 
            "Quienes_pueden_entrevistar", "Speech_de_confirmacion", "fecha_creacion"
        ]
        
        for key, value in doc.items():
            if key not in exclude_fields:
                # Map new field names back to old field names for response
                mapped_key = FIELD_MAPPING_RESPONSE.get(key, key)
                result[mapped_key] = value
                
        # Add availability status
        result["disponible"] = is_vacancy_available(doc)
        
    return result

# Base search function to reuse across field searches
def perform_field_search(field: str, value: str, es_client: OpenSearch, index: str = None, size: int = 10) -> List[Dict[str, Any]]:
    """
    Perform a search on a specific field across indices.
    """
    try:
        if not value:
            return []
        
        query = {
            "size": size,
            "query": {
                "wildcard": {field: f"*{value.lower()}*"}
            }
        }
        
        logger.debug(f"Field search query: {json.dumps(query)}")
        
        results = []
        indices = [index] if index else ["vacantefinal", "puestos"]
        
        # First search in vacantefinal to prioritize them
        if "vacantefinal" in indices:
            try:
                response = es_client.search(
                    index="vacantefinal",
                    body=query
                )
                
                for hit in response["hits"]["hits"]:
                    hit_source = hit["_source"]
                    hit_source["_id"] = hit["_id"]
                    hit_source["_index"] = hit["_index"]
                    results.append(hit_source)
                    
                logger.debug(f"Found {len(response['hits']['hits'])} results in vacantefinal for field {field}={value}")
                
            except Exception as e:
                logger.warning(f"Error searching index vacantefinal for field {field}: {e}")
        
        # Then search in puestos, but only if we need more results
        if "puestos" in indices and len(results) < size:
            try:
                available_id_puestos = get_available_id_puestos(es_client)
                
                if available_id_puestos:
                    puestos_query = {
                        "size": size - len(results),
                        "query": {
                            "bool": {
                                "must": [
                                    {"wildcard": {field: f"*{value.lower()}*"}},
                                    {"terms": {ID_PUESTO: available_id_puestos}}
                                ]
                            }
                        }
                    }
                    
                    response = es_client.search(
                        index="puestos",
                        body=puestos_query
                    )
                    
                    for hit in response["hits"]["hits"]:
                        hit_source = hit["_source"]
                        hit_source["_id"] = hit["_id"]
                        hit_source["_index"] = hit["_index"]
                        results.append(hit_source)
                        
                    logger.debug(f"Found {len(response['hits']['hits'])} results in puestos for field {field}={value}")
                
            except Exception as e:
                logger.warning(f"Error searching index puestos for field {field}: {e}")
        
        return results
    
    except Exception as e:
        logger.error(f"Error in perform_field_search for {field}={value}: {e}")
        return []

# Helper function to get all id_vacante values from vacantefinal
def get_available_id_puestos(es_client: OpenSearch) -> List[str]:
    """
    Get a list of id_vacante values from all vacancies.
    """
    try:
        query = {
            "size": 100,
            "query": {
                "match_all": {}
            },
            "_source": [ID_PUESTO, "Id_Puesto"]
        }
        
        response = es_client.search(
            index="vacantefinal",
            body=query
        )
        
        id_puestos = []
        for hit in response["hits"]["hits"]:
            id_puesto = hit["_source"].get(ID_PUESTO)
            if not id_puesto:
                # Check for old field name
                id_puesto = hit["_source"].get("Id_Puesto")
            if id_puesto:
                id_puestos.append(id_puesto)
                
        return id_puestos
        
    except Exception as e:
        logger.error(f"Error getting id_vacante values: {e}")
        return []

# Paginate results from puestos index
def paginated_vacantes_from_puestos(
    es, 
    puestos_query, 
    detail_level="summary", 
    offset=0, 
    limit=10
):
    """
    Paginate results from puestos index based on vacantefinal availability.
    """
    try:
        available_id_puestos = get_available_id_puestos(es)
        logger.debug(f"Available id_vacante from vacantefinal: {available_id_puestos}")
        
        if not available_id_puestos:
            logger.warning("No id_vacante found in vacantefinal")
            return []
        
        if "must" not in puestos_query["query"]["bool"]:
            puestos_query["query"]["bool"]["must"] = []
        puestos_query["query"]["bool"]["must"].append({"terms": {"Id_Puesto": available_id_puestos}})
        
        puestos_query["size"] = limit
        puestos_query["from"] = offset
        
        logger.debug(f"Final puestos query: {json.dumps(puestos_query)}")
        response = es.search(
            index="puestos",
            body=puestos_query
        )
        
        logger.debug(f"Puestos search returned {len(response['hits']['hits'])} hits")
        results = []
        for hit in response["hits"]["hits"]:
            hit_source = hit["_source"]
            hit_source["_id"] = hit["_id"]
            hit_source["_index"] = hit["_index"]
            results.append(hit_source)
        
        formatted_results = [format_document(doc, detail_level) for doc in results]
        
        return formatted_results
    
    except Exception as e:
        logger.error(f"Error in paginated_vacantes_from_puestos: {e}")
        return []

@mcp.tool()
def search_by_id_vacante(id_vacante: str, ctx: Context) -> str:
    """
    Search for a vacancy by id_vacante in vacantefinal index and return all text fields from the source document.
    """
    logger.info(f"SEARCH REQUEST: search_by_id_vacante called with ID: {id_vacante}")
    try:
        es = ctx.request_context.lifespan_context.es_client
        
        logger.info(f"INPUT VALIDATION: Requested vacancy ID={id_vacante}, type={type(id_vacante)}")
        
        query = {
            "size": 1,
            "query": {
                "term": {
                    "id_vacante": id_vacante
                }
            }
        }
        
        logger.info(f"QUERY: {json.dumps(query)}")
        response = es.search(
            index="vacantefinal",
            body=query
        )
        
        logger.info(f"RESPONSE: Found {response['hits']['total']['value']} results")
        
        if response["hits"]["total"]["value"] == 0:
            logger.warning(f"NO DATA: No vacancy found with id_vacante {id_vacante}")
            return json.dumps({"error": f"No vacancy found with id_vacante: {id_vacante}"})
        
        # Get the source document
        source = response["hits"]["hits"][0]["_source"]
        
        # Filter to return only text fields (strings)
        text_fields = {}
        for key, value in source.items():
            if isinstance(value, str):
                text_fields[key] = value
        
        logger.info(f"SUCCESS: Returning text fields for id_vacante {id_vacante}")
        return json.dumps(text_fields, cls=EsJSONEncoder)
        
    except Exception as e:
        error_msg = f"Error searching by id_vacante: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({"error": error_msg})

@mcp.tool()
def search_available_vacancies(ctx: Context, detail_level: str = "summary", offset: int = 0, limit: int = 10) -> str:
    """List all available vacancies."""
    logger.debug(f"Listing all available vacancies, detail_level: {detail_level}, offset={offset}, limit={limit}")
    try:
        es = ctx.request_context.lifespan_context.es_client
        query = {
            "size": limit,
            "from": offset,
            "query": {
                "match_all": {}
            }
        }
        response = es.search(
            index="vacantefinal",
            body=query
        )
        results = []
        for hit in response["hits"]["hits"]:
            hit_source = hit["_source"]
            hit_source["_id"] = hit["_id"]
            hit_source["_index"] = hit["_index"]
            results.append(hit_source)
        
        formatted_results = [format_document(doc, detail_level) for doc in results]
        
        total_hits = response["hits"]["total"]["value"]
        has_more = offset + limit < total_hits
        
        pagination_response = {
            "results": formatted_results,
            "total": total_hits,
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
            "instruction": (
                f"Showing {len(formatted_results)} of {total_hits} available vacancies. "
                + ("To see more results, call this tool again with offset=next_offset." if has_more else "No more results.")
            )
        }
        
        logger.info(f"Found {len(formatted_results)} available vacancies (offset={offset}, limit={limit}, total={total_hits})")
        return json.dumps(pagination_response, cls=EsJSONEncoder)
    except Exception as e:
        error_msg = f"Error listing available vacancies: {str(e)}"
        logger.error(error_msg)
        return json.dumps({"error": error_msg})

# Custom handler for MCP resource and tool requests
async def mcp_handler(request: Request):
    """Handle MCP resource and tool requests."""
    logger.debug(f"Processing MCP request: {request.url.path}")
    try:
        path = request.url.path
        method = request.method

        if path.startswith("/mcp/resource/"):
            resource_id = path[len("/mcp/resource/"):]
            if method == "GET":
                if resource_id == "schema://main":
                    result = get_schema()
                    return Response(content=result, media_type="text/plain")
                else:
                    return Response(content="Resource not found", status_code=404)

        elif path.startswith("/mcp/tool/"):
            tool_name = path[len("/mcp/tool/"):]
            if method == "POST":
                body = await request.json()
                ctx = Context(
                    request_context=type("RequestContext", (), {
                        "lifespan_context": request.app.state.mcp_context
                    })()
                )
                tools = {
                    "search_available_vacancies": search_available_vacancies,
                    "search_by_id_vacante": search_by_id_vacante,
                    "search_by_ad_id": search_by_ad_id,
                }
                
                if tool_name in tools:
                    result = tools[tool_name](**{**body, "ctx": ctx})
                    return Response(content=result, media_type="application/json")
                else:
                    return Response(content=f"Tool not found: {tool_name}", status_code=404)

        return Response(content="Invalid MCP request", status_code=400)
    except Exception as e:
        logger.error(f"Error handling MCP request: {e}", exc_info=True)
        return Response(content=f"Error: {str(e)}", status_code=500)

# Custom SSE endpoint for MCP communication
async def mcp_sse(request: Request):
    """Handle Server-Sent Events (SSE) for MCP communication."""
    async def event_stream():
        logger.debug("Starting SSE stream for /mcp")
        try:
            yield f"data: {json.dumps({'event': 'init', 'message': 'MCP Elasticsearch SSE connection established'})}\n\n"
            while True:
                yield f"data: {json.dumps({'event': 'ping', 'timestamp': time.time()})}\n\n"
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            logger.debug("SSE stream cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in SSE stream: {e}", exc_info=True)
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    logger.debug("Handling SSE request at /mcp")
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )

# Test SSE endpoint
async def test_sse(request: Request):
    """Test SSE endpoint for connectivity."""
    async def event_stream():
        yield f"data: {json.dumps({'message': 'Elasticsearch SSE test successful'})}\n\n"
    logger.debug("Serving test SSE endpoint")
    return StreamingResponse(event_stream(), media_type="text/event-stream")

# Status endpoint
async def status_handler(request: Request):
    """Simple health check endpoint."""
    logger.debug("Received status check request")
    try:
        es = OpenSearch(**ES_CONFIG)
        try:
            info = es.info()
            es_version = info.get("version", {}).get("number", "unknown")
            health = "healthy"
            details = {
                "es_version": es_version,
                "client_info": str(type(es)),
                "available_tools": [
                    "search_by_id_vacante",
                    "search_available_vacancies",
                    "search_by_ad_id",
                ]
            }
        except Exception as e:
            health = "degraded"
            details = {"error": str(e), "error_type": str(type(e))}
        es.close()
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        health = "unhealthy"
        details = {"error": str(e)}
    
    return Response(
        content=json.dumps({
            "status": health,
            "service": "MCP OpenSearch Server",
            "timestamp": datetime.datetime.now().isoformat(),
            "details": details
        }), 
        media_type="application/json"
    )

# Modified lifespan to store MCP context
async def app_lifespan_wrapper(app: Starlette):
    """Wrap the FastMCP lifespan to store context in Starlette app."""
    async with app_lifespan(mcp) as ctx:
        app.state.mcp_context = ctx
        yield

# Mount to Starlette ASGI server
app = Starlette(
    routes=[
        Route('/status', status_handler, methods=["GET"]),
        Route('/mcp', mcp_sse, methods=["GET"]),
        Route('/mcp/', mcp_sse, methods=["GET"]),
        Mount('/mcp-legacy', app=mcp.sse_app(), name="mcp_legacy"),
        Mount('/mcp-legacy/', app=mcp.sse_app(), name="mcp_legacy_slash"),
        Route('/test-sse', test_sse, methods=["GET"]),
        Route('/mcp/resource/{path:path}', mcp_handler, methods=["GET"]),
        Route('/mcp/tool/{path:path}', mcp_handler, methods=["POST"]),
    ],
    lifespan=app_lifespan_wrapper
)
app.add_middleware(LoggingMiddleware)

if __name__ == "__main__":
    import uvicorn
    mcp_port = int(os.getenv("MCP_PORT", "8000"))
    logger.info(f"Starting MCP Elasticsearch server on http://0.0.0.0:{mcp_port}")
    uvicorn.run(app, host="0.0.0.0", port=mcp_port)