# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

## Case điền

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID `E-seeded_regression-20261118-7b4d` |
| Triệu chứng | Lab 8 grader fail: `status resolved != denied`. `refund_amount_correct=False` (ledger 20.000 vs nhãn 0). Reply nói "đã hoàn 20.000đ" trong khi đơn O-202 chỉ trễ **2 ngày** → không đủ điều kiện. |
| Bước sai đầu tiên | **Event 3**, kind `model_override`, payload `{"delay_days": 5}`: agent lấy số ngày từ ticket ("trễ 5 ngày") thay vì `orders.delay_days = 2`. |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` và event 2 `investigator` đều đúng: investigator trả `O-202 status=delivered, delay_days=2`. Chỉ từ event 3 (override) trở đi mới sai: event 4 `quote` ra 20.000, event 6 `reply` báo 20.000. |
| Failure mode | **FM-03 `ticket_trust`** (`docs/failure_taxonomy.md`). |
| Đối chứng | `fixed C-002@11`: **không có** `model_override`; event 3 `quote {"amount_vnd": 0, "reason": "no_entitlement"}`; ledger 0, status `denied`; lab8 grader **PASS**. |
| Regression test | Eval item **`E-002`** (C-002, nhãn `denied/refund 0`) trong `eval_set_v1`, chấm bằng `RefundAmountCorrect` + `ProposalAmountCorrect` và `pass_rate`. Unit test tương ứng: `tests/test_lab9_graders.py::test_wrong_amount_in_ledger`. Đã thấy **fail** trên `seeded_regression` và **pass** trên `fixed` qua `reports/eval_*.json` và `lab9.mutation --detect` (detection 100%). |
| Chưa chắc chắn | Trace chỉ chứng minh **logic** ticket-over-DB trên MockLLM deterministic; không chứng minh model thật cũng sai như vậy. Trace không cho biết vì sao agent chọn ticket — chỉ biết nó đã override. |

## Quy tắc
- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" dẫn số event cụ thể (event 3), không phải "agent bị nhầm".
- Case hoàn thành khi có regression test chạy được: ở đây là item `E-002` + các grader code, tái lập bằng `python -m lab9.eval --shape seeded_regression` và `--shape fixed`.