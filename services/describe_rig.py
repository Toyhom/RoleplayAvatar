"""Choose the face view first, then locate landmarks in a magnified crop."""

import argparse
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument("--job", type=Path, required=True)
args = parser.parse_args()
landmark_file = args.job / "face-landmarks-mp.json"
if landmark_file.is_file():
    detected = json.loads(landmark_file.read_text())
    views = [view for view in ("front", "back") if detected[view].get("detected")]
    if len(views) == 1:
        view = views[0]
        result = {
            **detected[view],
            "view": view,
            "head_joint": None,
            "jaw_joint": None,
            "face_visible": True,
            "method": "MediaPipe landmarks with geometric consistency checks",
            "notes": "Head joint selected from actual skin influence; no VLM probability used.",
        }
        (args.job / "rig-analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print("RIG_ANALYSIS_READY mediapipe", flush=True)
        raise SystemExit(0)

sys.modules["flash_attn"] = None
import torch
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor

processor = AutoProcessor.from_pretrained(args.model, local_files_only=True)
model = AutoModelForImageTextToText.from_pretrained(
    args.model,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    attn_implementation="sdpa",
    local_files_only=True,
).eval()


def ask(images, prompt, name):
    content = [{"type": "image", "image": str(image)} for image in images]
    content.append({"type": "text", "text": prompt})
    inputs = processor.apply_chat_template(
        [{"role": "user", "content": content}],
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    ).to(model.device)
    with torch.inference_mode():
        result = model.generate(**inputs, max_new_tokens=600, do_sample=False)
    raw = processor.batch_decode(result[:, inputs["input_ids"].shape[-1] :], skip_special_tokens=True)[0]
    (args.job / (name + ".raw.txt")).write_text(raw)
    return json.loads(raw[raw.index("{") : raw.rindex("}") + 1])


choice = ask(
    [args.job / "mesh-front.png", args.job / "mesh-back.png"],
    "图1和图2是同一个3D角色的两面。哪张图能看到脸上的眼睛和嘴巴，而不是后脑勺或背部？"
    '只输出JSON：{"face_image":1或2或0,"confidence":0到1,"reason":"简短可见依据"}。'
    "请根据眼睛、鼻子、嘴巴判断，不要根据文件名；如果两张都看不到脸返回0。",
    "view-choice",
)
selected = choice.get("face_image")
view = "front" if selected == 1 else "back"
result = {
    "view": view,
    "head_joint": None,
    "jaw_joint": None,
    "confidence": 0,
    "face_visible": False,
    "notes": choice.get("reason", ""),
    "method": "separate view selection and face crop",
}
if selected in (1, 2):
    original = Image.open(args.job / f"mesh-{view}.png")
    width, height = original.size
    crop = (int(width * 0.25), int(height * 0.035), int(width * 0.75), int(height * 0.40))
    face_path = args.job / "face-crop.png"
    original.crop(crop).resize((768, 560)).save(face_path)
    landmarks = ask(
        [face_path],
        "这是3D角色的头部放大图。定位脸本身（不包括头发耳朵）的外接框，以及画面左眼中心、右眼中心、嘴中心。"
        "坐标均按整张图归一化到0至1000的整数，原点左上角，x向右，y向下。"
        '只输出JSON：{"face_visible":true或false,"face_box":[x1,y1,x2,y2],'
        '"left_eye":[x,y],"right_eye":[x,y],"mouth":[x,y],"confidence":0到1,"notes":"简短说明"}。'
        "如果没有明确的两只眼睛和嘴巴，返回face_visible=false，不要猜测。",
        "face-landmarks",
    )

    def point(p):
        return [
            (crop[0] + p[0] / 1000 * (crop[2] - crop[0])) / width,
            (crop[1] + p[1] / 1000 * (crop[3] - crop[1])) / height,
        ]

    if landmarks.get("face_visible"):
        box = landmarks["face_box"]
        result.update({key: point(landmarks[key]) for key in ("mouth", "left_eye", "right_eye")})
        result.update(
            face_visible=True,
            face_width=(box[2] - box[0]) / 1000 * (crop[2] - crop[0]) / width,
            confidence=min(choice.get("confidence", 0), landmarks.get("confidence", 0)),
            notes=landmarks.get("notes", ""),
        )
(args.job / "rig-analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
print("RIG_ANALYSIS_READY", json.dumps(result, ensure_ascii=False), flush=True)
