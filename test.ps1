$ErrorActionPreference = "Stop"

try {
    Write-Host "Starting session..."
    $startResponse = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/voice/start" -Method Post -ContentType "application/json" -Body "{}"
    $sessionId = $startResponse.session_id
    Write-Host "Session ID: $sessionId"
    
    $chatBody = @{
        session_id = $sessionId
        user_transcript = "hello"
    } | ConvertTo-Json
    
    Write-Host "Sending chat..."
    $chatResponse = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/voice/chat" -Method Post -ContentType "application/json" -Body $chatBody
    Write-Host "Chat Response:"
    $chatResponse | ConvertTo-Json -Depth 5 | Write-Host
} catch {
    Write-Host "Error occurred:"
    Write-Host $_.Exception.Message
    if ($_.ErrorDetails) {
        Write-Host "Error Details:"
        Write-Host $_.ErrorDetails.Message
    }
}
