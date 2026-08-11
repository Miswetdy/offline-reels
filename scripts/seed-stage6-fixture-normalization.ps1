[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$code = @'
from datetime import UTC, datetime
from uuid import uuid4
from app.core.settings import get_settings
from app.db.models.instagram import InstagramNormalizationJob, InstagramReel
from app.db.models.video import Video
from app.db.session import create_session_factory
sessions = create_session_factory(get_settings())
identifier = uuid4().hex[:16]
with sessions.begin() as db:
    video = Video(title='Fixture ready video', object_key=f'fixtures/{identifier}.mp4', content_type='video/mp4', byte_size=1)
    db.add(video)
    db.flush()
    reel = InstagramReel(shortcode=f'FIXTURE_{identifier}', canonical_url=f'https://example.invalid/reel/{identifier}', pipeline_status='ready', source_object_key=f'fixtures/source-{identifier}.mp4', source_sha256='a'*64, source_byte_size=1, video_id=video.id, ready_at=datetime.now(UTC))
    db.add(reel)
    db.flush()
    db.add(InstagramNormalizationJob(reel_id=reel.id, status='completed', attempt_count=1, completed_at=datetime.now(UTC)))
'@
docker compose -f deploy/docker-compose.stage6-smoke.yml exec -T api `
    uv run --no-sync python -c $code
if ($LASTEXITCODE -ne 0) { throw 'STAGE6_FIXTURE_NORMALIZATION_SEED_FAILED' }
Write-Output 'STAGE6_FIXTURE_NORMALIZATION_SEEDED'
