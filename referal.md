# Referal

### Messenger
referral.ref (de Messenger) → se guarda en current_job_interest.
current_ad_id se usa para controlar el flujo de la vacante en el backend.
No hay una relación directa en el código, pero ambos están ligados al contexto de la vacante y la postulación.
En el webhook /webhook-messenger, cuando procesas el evento, revisa si existe el objeto referral y extrae el campo ref. Así puedes asociar el usuario con el anuncio o campaña de origen.
```
if 'referral' in messaging_event:
    referral_ref = messaging_event['referral'].get('ref')
    # Puedes guardar referral_ref en el estado de la sesión
```

### Formato: En la pagina bussines.facebook.com de la liga se puede sacar el page_id
```
https://m.me/<PAGE_ID>?ref=test123
```

### Link para pruebas con la pagina de TOP control
```
https://m.me/61574403483430?ref=120228908704830333
```


Hola Devie ! ¿Cómo puedo ayudarte? Puedes preguntarme cosas como:
¿Cuál es el sueldo y beneficios?
¿Qué requisitos necesito?
¿Cómo postulo al puesto?

### link pagina de GPScontrol
```
https://m.me/198119606930790?ref=120228908704830333
```

