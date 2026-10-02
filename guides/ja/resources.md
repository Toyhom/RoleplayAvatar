# キャラクターリソース

[English](../resources.md) · [简体中文](../zh-CN/resources.md) · [日本語](resources.md)

## デモ用ライブラリ

| キャラクター | 出典 | 機能 |
| --- | --- | --- |
| Haru、Hiyori | [Live2D CubismWebSamples](https://github.com/Live2D/CubismWebSamples/tree/b1de66b0b1f1cb881d95fb6158622aeb6a2827bd) | 口、目、眉、頭・体のパラメータ、物理、表情、動作 |
| RobotExpressive | [three.js / Quaternius / Don McCurdy](https://github.com/mrdoob/three.js/tree/157f0885b8428b5ffe8f6f7309b2d6f59faa1497/examples/models/gltf/RobotExpressive) | 14 種類のアニメーション、骨格、3 種類の顔モーフ |

固定 URL とチェックサムは `configs/demo-assets.json` にあります。ダウンロード、参照音声生成、インポートの順に実行します。

```bash
python scripts/fetch_demo_characters.py
# GPU ランナーで音声生成を実行する例：
gpuq submit --node auto --name avatar-demo-voices --gpus 1 -- bash "$PWD/scripts/design_demo_voices.sh"
# 音声ジョブ完了後：
python scripts/import_demo_characters.py
```

Live2D サンプルは [Free Material License](https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html) と [Sample Model Terms](https://www.live2d.com/eula/live2d-sample-model-terms_en.html)、Cubism Core は [Live2D Proprietary Software License](https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html) を使用します。参照音声と会話設定はフレームワークが別途作成します。RobotExpressive は CC0-1.0 です。

> This content uses sample data owned and copyrighted by Live2D Inc. The sample data are utilized in accordance with terms and conditions set by Live2D Inc. This content itself is created at the author’s sole discretion.

## Live2D ZIP の読み込み

画面で **2D キャラクター → Live2D ZIPをインポート** を選びます。ディレクトリ構造を維持し、次を含めます。

- `.model3.json` と `.moc3`。
- マニフェストが参照するテクスチャ。
- 参照される物理、ポーズ、表情、動作と音声。
- `licenses/` などに出典とライセンス文書。

通常は一つの ZIP から一つのモデルを選びます。複数の場合は API の `model_entry` を使います。パス、容量、参照先、テクスチャ、moc3 の署名を検証した後、設定と声の候補を生成します。インストール済み Cubism Core と互換性のあるモデルを選んでください。

口パクは `LipSync` グループまたは `ParamMouthOpenY` を使います。独自 ID は `profile.json` の `live2d_parameter_map` で対応付けられます。描画は元のパラメータ、動作、物理に従います。

## 自動生成する 2D 立ち絵

画像処理では元画像の唇のメッシュで連続的に口を動かす立ち絵を作ります。フレームワーク独自の 2D リギング形式を使います。作者が設定した視点変化、遮蔽、服の詳細な動きを利用する場合は、ネイティブ Cubism モデルをインポートできます。

キャラクターは `presentation_modes=["2d"]` または `["3d"]` の一方を持ちます。両方必要なら別々に作成します。

## キャラクターパッケージ

八つの基本ファイルは `profile.json`、`capabilities.json`、`rig_map.json`、`face_map.json`、`motion_manifest.json`、`voice_profile.json`、`provenance.json`、`qa_report.json` です。スキーマは `schemas/` にあります。

立ち絵には `puppet/`、Live2D には `live2d/`、3D には `model.glb` が含まれます。書き出しは参照素材、声の候補、ライセンス、出典を保持します。移行先で対応レンダラーを用意し、`avatar validate PATH --require-assets` で確認します。

全体の出典とライセンスは [NOTICE](../../NOTICE.md) にあります。

[← ガイド一覧](index.md)
