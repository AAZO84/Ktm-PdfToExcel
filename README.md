# PDF → Excel (FastAPI) listo para Railway

Convierte facturas en PDF a Excel.  
Sube el PDF desde tu computadora (navegador) y descarga el .xlsx resultante.

## 🚀 Despliegue en Railway
1. Crea un repositorio en GitHub con estos archivos.
2. Entra a Railway → New Project → Deploy from GitHub.
3. Railway detectará Python y usará el Procfile automáticamente.
4. Cuando termine el deploy, abre la URL pública.
5. Prueba:
   - `/` → formulario para subir PDF
   - `/convert` → endpoint POST
   - `/docs` → Swagger
   - `/health` → estado del servicio
