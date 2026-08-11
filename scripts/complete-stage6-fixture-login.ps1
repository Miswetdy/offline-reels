[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($env:STAGE6_ACCOUNT_ID)) { throw 'STAGE6_ACCOUNT_ID_UNAVAILABLE' }
$code = @"
from datetime import UTC, datetime
from uuid import UUID
from app.core.settings import get_settings
from app.db.models.instagram import InstagramAccount
from app.db.session import create_session_factory
from app.instagram.contracts import AccountStatus
sessions = create_session_factory(get_settings())
with sessions.begin() as db:
    account = db.get(InstagramAccount, UUID('$env:STAGE6_ACCOUNT_ID'))
    assert account is not None
    account.status = AccountStatus.CONNECTED.value
    account.reason_code = None
    account.last_connected_at = datetime.now(UTC)
"@
docker compose -f deploy/docker-compose.stage6-smoke.yml exec -T api `
    uv run --no-sync python -c $code
if ($LASTEXITCODE -ne 0) { throw 'STAGE6_FIXTURE_LOGIN_COMPLETE_FAILED' }
Write-Output 'STAGE6_FIXTURE_LOGIN_COMPLETED'
