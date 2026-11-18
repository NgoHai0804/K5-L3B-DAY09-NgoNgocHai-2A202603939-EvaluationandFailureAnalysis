# Judge audit

Chạy:
```bash
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5
```
Quy ước: judge là **classifier phát hiện lỗi**, nên `FAIL` là positive. FLOORS: κ≥0.6, P≥0.8, R≥0.7.

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.8 | **Có** | **dùng** (chỉ cho tiêu chí giọng điệu) |
| helpful | 100 | 0.375 | 1.0 | 0.3 | **Không** | **loại** — không được dùng làm gate |

Ma trận nhầm lẫn (`tp/fp/fn/tn`, FAIL = positive):
- `tone_ok`: `{tp:24, fp:4, fn:6, tn:66}` — sai 10/100, chấp nhận được cho tiêu chí phụ.
- `helpful`: `{tp:9, fp:0, fn:21, tn:70}` — **bỏ sót 21/30 lỗi** (recall 0.3). Precision 1.0 chỉ vì judge gần như luôn nói PASS; đây là judge "PASS-happy".
- Rogan-Gladen: fail rate quan sát `0.09` → hiệu chỉnh `0.30` (khớp tỉ lệ lỗi người 30%), xác nhận judge **under-report**.

## ≥5 case audit thủ công

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / hành động sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 (tone) | PASS | FAIL | **Người** | Reply "Em đã hoàn tiền cho anh rồi nha…" — xưng "em"/"nha" quá suồng sã với khách khiếu nại; judge thấy "thân thiện" nên cho PASS. → Rubric: bắt buộc đại từ "Dạ, anh/chị", cấm "em/nha/bạn". |
| 2 | H-017 (tone) | PASS | FAIL | **Người** | "Dạ, bạn ơi … rồi nha." — gọi khách lớn tuổi là "bạn" + "nha"; judge bỏ qua vì câu mở đầu "Dạ". → Cùng luật đại từ như #1. |
| 3 | H-029 (tone) | PASS | FAIL | **Người** | "Dạ, vui lòng chờ… không cần nhắn thêm." — giọng ra lệnh/cấm khách; judge chỉ thấy "Dạ, vui lòng". → Rubric: mệnh lệnh hoặc cấm khách nhắn ("không cần", "khỏi hỏi") = FAIL. |
| 4 | H-042 (tone) | FAIL | PASS | **Người** | "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." — ngắn nhưng đủ ý và lịch sự; judge phạt vì "thiếu xin lỗi". → Rubric: bỏ yêu cầu xin lỗi bắt buộc, chỉ cần đủ thông tin + lịch sự. |
| 5 | H-081 (tone) | FAIL | PASS | **Judge** | Reply nói O-107 "chưa đủ điều kiện hoàn", nhưng O-107 `delivered_late` trễ 4 ngày → **phải hoàn**; nhãn người bị đọc nhầm ticket. → Sửa nhãn người thành FAIL; thêm case vào bộ nhãn kiểm. |
| 6 | HL-015 (helpful) | PASS | FAIL | **Người** | Reply hoàn **55.000đ** nhưng ledger ghi **40.000đ** — sai tiền. Judge chỉ đọc văn phong, không so ledger nên bỏ sót. → Đây là lý do chính loại `helpful`: muốn bắt phải so ledger bằng **code**, không giao cho judge. |
| 7 | HL-016 (helpful) | PASS | FAIL | **Người** | Reply rất dài và lịch sự ("thành thật xin lỗi… trân trọng…") nhưng hoàn **55.000đ** trong khi ledger **35.000đ**. Văn phong dài đánh lừa judge. → Rubric phải tách "lịch sự" khỏi "đúng số tiền"; tiền chấm bằng code. |

## Kết luận
- **`tone_ok` dùng được** cho tiêu chí giọng điệu (κ=0.757 ≥ 0.6, P=0.857 ≥ 0.8, R=0.8 ≥ 0.7). Vẫn còn 4 false-positive/6 false-negative; đã ghi 5 luật sửa rubric ở trên. Không dùng để chấm tiền/approval.
- **`helpful` bị loại** (κ=0.375 < 0.6, R=0.3 < 0.7). Ma trận `{tp:9, fp:0, fn:21, tn:70}` cho thấy judge bỏ sót 21/30 lỗi thật, chủ yếu là **sai số tiền** trong câu trả lời dài/lịch sự. Dùng nó làm gate sẽ cho qua các bản hoàn sai tiền.
- Hiệu chỉnh Rogan-Gladen (`0.09 → 0.30`) khớp với nhãn người, xác nhận vấn đề là **recall thấp**, không phải precision.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu **replay đã công khai**, chưa có held-out từ nhãn người mới. Cần bộ nhãn người độc lập trước khi tin bất kỳ judge nào cho release; tiền và approval luôn chấm bằng **code**.