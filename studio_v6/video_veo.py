"""Official Gemini/Veo API generation. Not the Google Flow website or Flow credits."""
from pathlib import Path
import os
import time


def generate_veo(prompt: str, destination: Path, reference: Path | None = None,
                 sleep_seconds: int = 10, max_wait_seconds: int = 900) -> str:
    key = os.getenv('GEMINI_API_KEY','').strip()
    if not key:
        raise RuntimeError('ยังไม่มี GEMINI_API_KEY; ไม่ได้สร้างคลิปจริง')
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError('ติดตั้ง google-genai ก่อน') from exc
    client = genai.Client(api_key=key)
    config = types.GenerateVideosConfig(aspect_ratio='9:16', duration_seconds=8, resolution='720p')
    prompt = (prompt + '\nCreate a natural 8-second vertical 9:16 video, with Thai voiceover when possible. '
              'Use authentic handheld first-person POV hands operating the item. '
              'No static listing picture as a scene or thumbnail. No made-up product claims.')
    kwargs = {'model': os.getenv('VEO_MODEL','veo-3.1-fast-generate-preview'),
              'prompt':prompt, 'config':config}
    # Reference image can be attached as an asset reference, not placed directly as frame one.
    if reference and reference.exists():
        try:
            kwargs['config'] = types.GenerateVideosConfig(
                aspect_ratio='9:16', duration_seconds=8, resolution='720p',
                reference_images=[types.VideoGenerationReferenceImage(
                    image=types.Image.from_file(location=str(reference)), reference_type='asset')])
        except (AttributeError, TypeError, ValueError) as exc:
            raise RuntimeError('อัปโหลดภาพอ้างอิงให้ Veo ไม่สำเร็จ; หยุดก่อนเพื่อไม่สร้างสินค้าผิดแบบ') from exc
    operation = client.models.generate_videos(**kwargs)
    deadline = time.monotonic() + max_wait_seconds
    while not operation.done:
        if time.monotonic() > deadline:
            raise TimeoutError('Veo ใช้เวลานานเกินกำหนด; ตรวจงานในบัญชี Google ก่อนสั่งซ้ำ')
        time.sleep(sleep_seconds)
        operation = client.operations.get(operation)
    videos = getattr(getattr(operation,'response',None),'generated_videos',None)
    if not videos:
        raise RuntimeError('Veo ไม่ส่งวิดีโอกลับมา; ตรวจรายละเอียดงานใน Google API')
    destination.parent.mkdir(parents=True,exist_ok=True)
    client.files.download(file=videos[0].video, destination=str(destination))
    if not destination.exists() or destination.stat().st_size < 1000:
        destination.unlink(missing_ok=True)
        raise RuntimeError('ไฟล์ MP4 จาก Veo ไม่มีข้อมูล')
    return getattr(operation,'name','') or ''
