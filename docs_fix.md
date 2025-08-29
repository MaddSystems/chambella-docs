### Ports for MCP

SSE new PORT from 9000 to 8000

0. main.py 
 func -> search_by_ad_id

1.job_discovery_agent
 func -> get_available_vacantes -> MCP: search_available_vacancies (Get a paginated list of available job vacancies from the MCP server)
 "name": "get_available_vacantes",
        "response": {
          "pagination": {},
          "status": "success",
          "vacantes": [
            {
              "job_id": "36",
              "title": "Custodio 1°"
            },
            {
              "job_id": 151,
              "title": "Operador de camioneta"
            },
            {
              "job_id": 22,
              "title": "Monitorista de GPS"
            },
            {
              "job_id": 57,
              "title": "Maniobrista"
            },
            {
              "job_id": 70,
              "title": "Mensajero"
            },
            {
              "job_id": 38,
              "title": "Custodio 2° Sr"
            }
          ] 

 func -> select_job (Selects a job, updates the session state, and transfers to the job_info_agent)

2. job_info_agent: 
 func -> get_job_details_by_id(current_job_id, tool_context) -> MCP: search_by_id_puesto -> return {"status": "success", "job_details": result_data}
 func -> load_job_info(current_job_id) -> get_job_details_by_id(current_job_id, tool_context) -> job_details_response 
 job_data = job_details_response["job_details"]

 current_interest = {
            "id": str(job_data.get("Id_Puesto", current_job_id)),
            "title": job_title,
            "company": job_data.get("Empresa"),
            "location": job_data.get("Ubicacion", job_data.get("Oficinas")),
            "description": job_data.get("Descripcion_Puesto", job_data.get("Objetivo_del_puesto")),
            "functions": job_data.get("Funciones"),
            "responsibilities": job_data.get("Responsabilidades"),
            "salary_min": job_data.get("Sueldo_Neto_Min"),
            "salary_max": job_data.get("Sueldo_Max"),
            "experience_level": job_data.get("Experiencia_minima"),
            "employment_type": job_data.get("Jornada_Laboral"),
            "available": job_data.get("disponible", True)
        }
 func -> check_user_data (check state of name, last name, phone)
  

3.application_agent
 func -> get_current_time
 func -> get_available_interview_slots -> get_job_details_by_id -> MCP: search_by_id_puesto -> return {"status": "success", "job_details": result_data}
      dias_entrevista_str = job_data.get("Dias_para_atender_Entrevistas", "")
      horarios_disponibles_str = job_data.get("Horarios_disponibles_para_Entrevistar", "")

 func -> update_interview_selection (Updates the state with user's selection for interview date or time.)

mcp_elasticsearch_sse 