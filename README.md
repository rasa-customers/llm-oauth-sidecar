# Azure OpenAI Authentication Proxy

A lightweight authentication proxy server that adds Azure AD certificate-based authentication to OpenAI-compatible API requests. Designed to run as a Kubernetes sidecar container for applications using LiteLLM SDK.

## Overview

This proxy sits between your application and Azure OpenAI API, automatically handling:
- Azure AD token acquisition using certificate credentials
- Automatic token refresh before expiration (every ~55 minutes)
- Transparent request/response passthrough
- All HTTP methods and endpoints

## Quick Start

### Using Docker

1. **Build the container:**
```bash
docker build -t auth-proxy .
```

2. **Run with your configuration:**
```bash
docker run -d \
  -p 8080:8080 \
  -e AZURE_CLIENT_ID=your-client-id \
  -e AZURE_TENANT_ID=your-tenant-id \
  -e AZURE_CERTIFICATE_PATH=/app/certs/cert.pem \
  -e API_BASE_URL=https://your-azure-openai.openai.azure.com \
  -v /path/to/your/certificate:/app/certs:ro \
  auth-proxy
```

### Using Docker Compose

1. **Set environment variables:**
```bash
export AZURE_CLIENT_ID="your-client-id"
export AZURE_TENANT_ID="your-tenant-id"
```

2. **Place your certificate in `./certs/certificate.pem`**

3. **Update `API_BASE_URL` in docker-compose.yml**

4. **Run:**
```bash
docker-compose up -d
```

## Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `AZURE_CLIENT_ID` | Azure AD application client ID | `12345678-1234-1234-1234-123456789012` |
| `AZURE_TENANT_ID` | Azure AD tenant ID | `87654321-4321-4321-4321-210987654321` |
| `AZURE_CERTIFICATE_PATH` | Path to certificate PEM file inside container | `/app/certs/cert.pem` |
| `API_BASE_URL` | Destination Azure OpenAI API base URL | `https://myservice.openai.azure.com` |

### Optional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `HOST` | Host to bind the proxy server | `0.0.0.0` |
| `PORT` | Port for the proxy server | `8080` |
| `AZURE_SCOPE` | Azure AD scope for token requests | `https://cognitiveservices.azure.com/.default` |

## Usage with Rasa

Simply point your Rasa client to the proxy:

```yaml
- id: gpt-4o-mini-2024-07-18
    models:
      - provider: azure
        deployment: gpt-4o-mini-2024-07-18
        api_base: http://proxy_server_url:8080
        api_version: 2024-03-01-preview
        api_key: ${API_KEY} 
```

## Azure AD Setup

### Prerequisites

1. **Azure AD Application Registration:**
   - Create an application registration in Azure AD
   - Note the Application (client) ID and Directory (tenant) ID

2. **Certificate Setup:**
   - Generate a certificate or use existing one
   - Upload the certificate to your Azure AD application
   - Ensure you have the private key in PEM format

3. **API Permissions:**
   - Grant your application appropriate permissions for Azure OpenAI
   - Ensure the service principal has access to your Azure OpenAI resource

### Certificate Format

The certificate must be in PEM format:
```
-----BEGIN CERTIFICATE-----
[certificate content]
-----END CERTIFICATE-----
-----BEGIN PRIVATE KEY-----
[private key content]
-----END PRIVATE KEY-----
```

## Kubernetes Deployment

### As a Sidecar Container

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  template:
    spec:
      containers:
      # Your main application
      - name: app
        image: your-app:latest
        env:
        - name: OPENAI_BASE_URL
          value: "http://localhost:8080"
        
      # Auth proxy sidecar
      - name: auth-proxy
        image: auth-proxy:latest
        ports:
        - containerPort: 8080
        env:
        - name: AZURE_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: azure-credentials
              key: client-id
        - name: AZURE_TENANT_ID
          valueFrom:
            secretKeyRef:
              name: azure-credentials
              key: tenant-id
        - name: AZURE_CERTIFICATE_PATH
          value: "/app/certs/cert.pem"
        - name: API_BASE_URL
          value: "https://your-azure-openai.openai.azure.com"
        volumeMounts:
        - name: azure-cert
          mountPath: /app/certs
          readOnly: true
      volumes:
      - name: azure-cert
        secret:
          secretName: azure-certificate
```

### Create Kubernetes Secrets

```bash
# Create credentials secret
kubectl create secret generic azure-credentials \
  --from-literal=client-id="your-client-id" \
  --from-literal=tenant-id="your-tenant-id"

# Create certificate secret
kubectl create secret generic azure-certificate \
  --from-file=cert.pem=path/to/your/certificate.pem
```

## API Endpoints

The proxy passes through all endpoints to the destination API:

- `POST /v1/chat/completions` - Chat completions
- `POST /v1/completions` - Text completions  
- `GET /v1/models` - List models
- Any other endpoint supported by your destination API

### Health Check

- `GET /health` - Returns `{"status": "ok"}` when proxy is ready

## How It Works

1. **Startup**: Proxy obtains initial Azure AD access token using certificate
2. **Request Handling**: 
   - Application sends request to `http://localhost:8080/any/endpoint`
   - Proxy adds `Authorization: Bearer <token>` header
   - Request forwarded to destination API unchanged
   - Response returned to application unchanged
3. **Token Management**: Background thread refreshes token every 30 minutes (5 minutes before expiry)

## Development

### Local Development

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Set environment variables:**
```bash
export AZURE_CLIENT_ID="your-client-id"
export AZURE_TENANT_ID="your-tenant-id"
export AZURE_CERTIFICATE_PATH="/path/to/cert.pem"
export API_BASE_URL="https://your-azure-openai.openai.azure.com"
```

3. **Run the proxy:**
```bash
python proxy_server.py
```

### Testing

Test the proxy with curl:

```bash
# Health check
curl http://localhost:8080/health

# Test API call (replace with your model)
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Troubleshooting

### Common Issues

**1. "Missing required Azure AD configuration"**
- Verify all required environment variables are set
- Check that certificate file exists at specified path

**2. Token acquisition fails**
- Verify certificate format (should be PEM with both cert and private key)
- Check Azure AD application permissions
- Ensure certificate is uploaded to Azure AD application

**3. API calls return 401/403**
- Verify the service principal has access to Azure OpenAI resource
- Check that the scope matches your API requirements

**4. Connection refused**
- Verify `API_BASE_URL` is correct and accessible
- Check network connectivity from container to destination API

### Debugging

Enable debug output by checking the container logs:

```bash
# Docker
docker logs <container-id>

# Kubernetes
kubectl logs <pod-name> -c auth-proxy
```

Look for log messages about:
- Token refresh events
- Request forwarding
- Authentication errors

## Security Considerations

- **Certificate Security**: Store certificates in Kubernetes secrets, never in container images
- **Network Security**: Use the sidecar pattern to avoid exposing the proxy externally
- **Principle of Least Privilege**: Grant minimal required permissions to the Azure AD service principal
- **Monitoring**: Monitor for authentication failures and token refresh issues

## Performance

- **Latency**: Adds ~1-2ms overhead per request
- **Memory**: ~30MB baseline memory usage
- **CPU**: Minimal CPU usage when idle
- **Concurrency**: Handles concurrent requests with async processing
