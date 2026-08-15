# Retail video datasets for evaluation

Research snapshot: **2026-08-15**. This review covers evaluation data, not permission to use it.
The owner and legal counsel must approve each dataset before download, processing, publication, or
commercial use. No dataset or media is vendored in this repository.

## How to read this review

Facts below point to a publisher-controlled dataset page, license, or paper. Every linked source was
accessed on **2026-08-15**. “Supported” means the publisher supplies the stated labels or benchmark;
“proposed” means this project could construct a test from the material, but the publisher does not
supply ground truth for that test. Unknown terms are not permission.

## Comparison

| Dataset | Content and scale | Publisher-provided annotations and splits | Terms, redistribution, and access | Retail relevance | Supported evaluation tasks | Project-proposed uses and limits |
|---|---|---|---|---|---|---|
| **PhysicalAI-SmartSpaces, MTMC 2024–2026** | More than 280 hours of synchronized 1080p/30 FPS video from nearly 1,800 cameras. The collection is synthetic except for two short 2026 real-world warehouse test scenes; scene types include warehouses, hospitals, retail, and others. The publisher's per-release table gives 90/23/28 scenes and 953/504/353 cameras for 2024/2025/2026. [NVIDIA dataset card](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces/blob/main/README.md) | 2024 has 2D boxes and cross-camera IDs; 2025–2026 add 3D boxes, depth, and JSON calibration. The card enumerates train/validation/test scenes for 2025 and 2026. Ground truth is withheld for the two real 2026 scenes. [NVIDIA dataset card](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces/blob/main/README.md) | Dataset card declares **CC BY 4.0**; attribution is required and redistribution is allowed under that license. Files are directly hosted on Hugging Face; RGB-only download avoids the multi-terabyte depth payload. [Dataset card](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces/blob/main/README.md), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/legalcode) | Some 2024 sequences contain a primary retail space and connected storage room, but recent named scenes are predominantly warehouses. The object classes are people and industrial vehicles, not products or shelf interactions. [NVIDIA dataset card](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces/blob/main/README.md) | Publisher-supported: multi-camera multi-object tracking and 2D/3D detection; official evaluation uses location- or 3D-box-based HOTA. [NVIDIA dataset card](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces/blob/main/README.md) | Proposed: decoder/ingest, calibration, trajectory, occupancy, dwell, flow, zone, load, and cross-camera handoff tests. These require project-authored rules and ground truth mapping; do not present them as dataset benchmarks. It does **not** supply retail event, question, answer, evidence-citation, or faithfulness labels. |
| **RetailAction** | 21,000 real-store samples (about 41 hours) from more than 10,000 shoppers in 10 US convenience stores. Each sample contains two synchronized, ceiling-mounted views, each reduced to at most 32 motion-selected frames; faces and store identifiers are obscured. [Standard AI dataset card](https://huggingface.co/datasets/standard-cognition/RetailAction/blob/main/README.md) | Point locations and normalized temporal intervals for `take`, `put`, and `touch`, plus timestamps, motion scores, face positions, and subject pose. Published split: 17,222 train / 1,277 validation / 2,501 test, separated by anonymized shopper identity. The action distribution is severely imbalanced: 97.2% `take`, about 2% `put`, and less than 1% `touch`. [Standard AI dataset card](https://huggingface.co/datasets/standard-cognition/RetailAction/blob/main/README.md) | Hosted as three Hugging Face tar archives. The custom Standard.AI license permits use, modification, derivatives, and distribution subject to attribution, license-copy, notice, de-identification, and legal-compliance conditions. If revenue from a product or service using the material exceeds USD 10,000, further permission is required. [Dataset card](https://huggingface.co/datasets/standard-cognition/RetailAction/blob/main/README.md), [license](https://huggingface.co/datasets/standard-cognition/RetailAction/blob/main/LICENSE) **Owner/legal review required:** confirm how the revenue clause applies to evaluation and models, and resolve drafting anomalies in the license (including an unrelated “Meta” reference). Do not redistribute until reviewed. | Direct evidence of real convenience-store customer/product contact. It covers only three interaction types and short, heavily sampled clips. [Standard AI dataset card](https://huggingface.co/datasets/standard-cognition/RetailAction/blob/main/README.md) | Publisher-supported: multi-view spatiotemporal localization and classification of `take`, `put`, and `touch`; the published baseline reports joint, spatial, and temporal mAP. [Standard AI dataset card](https://huggingface.co/datasets/standard-cognition/RetailAction/blob/main/README.md) | Proposed: evaluate the first-release interaction detector and retrieval of the three labeled actions on validation/test only. It cannot test continuous ingestion, full visits, counts outside labeled clips, or natural-language answers. Shopper-disjoint splits do not establish store- or scene-disjointness; obtain store grouping from the publisher or treat cross-store generalization as unmeasured. |
| **MERL Shopping** | 106 fixed-overhead grocery-setting videos, each about two minutes long. [MERL research page](https://www.merl.com/research/highlights/merl-shopping-dataset) | Temporal instances of five actions: reach to shelf, retract from shelf, hand in shelf, inspect product, and inspect shelf. The publisher page does not document a canonical split or annotation-file schema. [MERL research page](https://www.merl.com/research/highlights/merl-shopping-dataset) | Publisher offers an FTP download “for research purposes” and requests citation of its CVPR 2016 paper. That sentence is not a complete license and does not state redistribution or commercial rights. [MERL research page](https://www.merl.com/research/highlights/merl-shopping-dataset), [publisher paper record](https://www.merl.com/publications/TR2016-080) **Owner/legal review required:** obtain the actual archive terms and written clarification before use; do not redistribute. | Real grocery-style, continuous overhead video with shelf-oriented actions; narrow in scale and action vocabulary compared with operational-store variation. The page establishes the setting and camera, but does not claim representative deployment coverage. [MERL research page](https://www.merl.com/research/highlights/merl-shopping-dataset) | Publisher-supported: temporal action detection—find each labeled action's start and stop in long video—rather than trimmed-clip classification alone. [MERL research page](https://www.merl.com/research/highlights/merl-shopping-dataset) | Proposed: continuous ingestion, temporal boundary, and action-across-window tests. Define and freeze a video-level split before tuning; never split chunks from one source video across train and evaluation. No questions, answer citations, product identity, or cross-camera labels are documented. |
| **UCF-Crime** (limited candidate) | 1,900 untrimmed surveillance videos totaling 128 hours, with 13 anomaly categories including shoplifting plus normal activity. The videos were collected from YouTube and the paper describes weak video-level labels. [Publisher paper](https://openaccess.thecvf.com/content_cvpr_2018/html/Sultani_Real-World_Anomaly_Detection_CVPR_2018_paper.html) | The paper defines anomaly detection/localization under weak video-level supervision and reports a train/test protocol; it does not provide retail interaction, track, question, or evidence-citation labels. [Publisher paper](https://openaccess.thecvf.com/content_cvpr_2018/html/Sultani_Real-World_Anomaly_Detection_CVPR_2018_paper.html) | The paper links the UCF project for data, but the paper itself grants no license or redistribution rights and source-video rights may differ. [Publisher paper](https://openaccess.thecvf.com/content_cvpr_2018/html/Sultani_Real-World_Anomaly_Detection_CVPR_2018_paper.html) **Owner/legal review required:** do not acquire or use until the publisher supplies applicable terms and provenance is approved. | Only the shoplifting subset is directly retail-related. “Anomaly” or “shoplifting” labels must not be converted into theft claims about people in this product. | Publisher-supported: video anomaly detection and temporal localization under the paper's protocol. [Publisher paper](https://openaccess.thecvf.com/content_cvpr_2018/html/Sultani_Real-World_Anomaly_Detection_CVPR_2018_paper.html) | **Do not use for the first release.** The product excludes theft claims, terms are unresolved, and the labels do not evaluate its supported retail events or answers. It is retained here only to prevent accidental use as a generic retail benchmark. |

## Integrity and leakage rules

1. **Split by source scene, not clip or camera.** All synchronized views of one physical or
   simulated scene belong to one split. Otherwise the same people, trajectories, layout, clock, and
   event can appear in both tuning and evaluation. RetailAction's two views must stay together, and
   MERL chunks derived from one original video must stay together. This is a project evaluation
   rule, not a claim that each publisher's published split enforces it.
2. **Group re-renders with their source.** PhysicalAI-SmartSpaces 2026 identifies scenes
   `001/003/005/007/021/024` as Cosmos Transfer 2.5 re-renders of
   `000/002/004/006/020/023`: they retain the scene, cameras, calibration, depth, and ground truth
   while changing RGB appearance. Treat each pair as one leakage group even though the published
   table places `Warehouse_023` in test and its `Warehouse_024` re-render in test as well. Do the
   same for any future re-render or derived clip. [NVIDIA dataset card](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces/blob/main/README.md)
3. **Apply the documented exclusion.** Exclude
   `MTMC_Tracking_2024/scene_071/camera_0649`; NVIDIA reports that video as corrupt. Record the
   exclusion in the immutable manifest, rather than silently skipping decode failures.
   [NVIDIA dataset card](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces/blob/main/README.md)
4. **Do not double-count AI City.** NVIDIA says the first PhysicalAI-SmartSpaces release was the
   dataset released for the 8th AI City Challenge. AI City results on that release are not an
   independent dataset result. [NVIDIA dataset card](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces/blob/main/README.md)
5. **Do not add an ambiguous “UCA” dataset.** No authoritative publisher and terms are identified
   in the current repository specifications. An acronym, mirror, paper citation, or third-party
   download is insufficient provenance. The owner must identify a primary dataset page and legal
   terms before it can enter a manifest.

Each immutable manifest should record publisher URL, exact revision/commit or retrieval timestamp,
license text and review decision, selected source scenes/videos and all grouping IDs, publisher
split, project split, checksums, exclusions, and allowed tasks. A manifest check should reject any
source-scene, synchronized-view, source-video, or re-render group assigned to multiple splits.

## Recommendations by evaluation task

There is no universal retail-video dataset.

| Evaluation decision | Recommended data | Why and boundary |
|---|---|---|
| File ingestion, decode, calibration, 2D/3D detection, single-/multi-camera tracking, trajectories, and load | **PhysicalAI-SmartSpaces RGB**, with scene/re-render groups held together and the corrupt camera excluded | It supplies synchronized cameras, calibration, boxes, IDs, and official tracking metrics. Report these as component results, not retail-answer quality. |
| Real-store `take` / `put` / `touch` localization | **RetailAction validation/test**, after license approval | It supplies direct real-store, multi-view spatial and temporal labels. Report per-class results because `put` and `touch` are rare. |
| Continuous shelf-action timing and events that cross inference-window boundaries | **MERL Shopping**, after terms are clarified, with video-level splits | Its two-minute sequences and action intervals test temporal boundaries better than RetailAction's sampled clips. |
| Theft, anomaly, or enforcement decisions | **None** | These decisions are outside the first release. UCF-Crime is not a shortcut to a supported product task. |
| Natural-language retail answers, evidence coverage, correctness, and abstention | **A consented, de-identified real-store holdout**, not any dataset above | The public candidates provide no questions paired with answers, camera/time evidence, or faithfulness and abstention labels. Hold out whole stores and time periods; include answerable and unanswerable questions, approved retail events, occlusion, crowds, lighting changes, camera faults, and synchronization failures. |

## Why component and synthetic data cannot replace the answer benchmark

An accurate box or cross-camera track establishes only that the component matched its annotation.
It does not establish that retrieval selected the right interval, that an event rule was valid, that
an answer's wording was supported, that every claim cited the correct camera and time range, or that
the system abstained when evidence was absent. PhysicalAI-SmartSpaces is predominantly synthetic
and its published annotations are geometric tracking/detection targets, while RetailAction and MERL
cover narrow action vocabularies without questions or cited answers. [NVIDIA dataset card](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces/blob/main/README.md), [Standard AI dataset card](https://huggingface.co/datasets/standard-cognition/RetailAction/blob/main/README.md), [MERL research page](https://www.merl.com/research/highlights/merl-shopping-dataset)

Synthetic scenes also omit or simplify the deployment distribution that determines answer quality:
store-specific layouts and policies, ambiguous human behavior, camera faults, privacy transforms,
and questions whose answer is outside the retained or visible evidence. This is a project risk
assessment, not a publisher claim. Use synthetic/component data to diagnose stages; use the locked
real-store holdout to decide whether evidence-backed retail answers are ready.
