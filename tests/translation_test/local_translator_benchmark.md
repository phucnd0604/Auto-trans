# Local Translator Benchmark

## Summary

| Scenario | Cold start (ms) | Single avg (ms) | Single p50 (ms) | Single p95 (ms) | Small batch (ms) | Throughput items/s | Mismatches |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| quickmt-en-vi | 2565.89 | 61.81 | 48.09 | 96.27 | 107.93 | 45.51 | 0 |
| opus-mt-en-vi-ctranslate2 | 421.72 | 316.51 | 303.46 | 585.9 | 334.8 | 5.58 | 0 |

## Samples

### quickmt-en-vi

- [subtitle_dialogue] `Masako: We have to go, or we'll lose him.`
  -> `Masako: Chúng ta phải đi, hoặc chúng ta sẽ mất anh ấy.` (103.86ms)
- [subtitle_dialogue] `Do you have news of your family's killers?`
  -> `Anh có tin tức về kẻ giết gia đình anh không?` (58.72ms)
- [subtitle_dialogue] `Because he is an ungrateful traitor.`
  -> `Vì hắn là kẻ phản bội vô ơn.` (50.65ms)
- [subtitle_dialogue] `After what happened at the inn, I didn't think you'd visit the temple again.`
  -> `Sau chuyện xảy ra ở quán trọ, tôi không nghĩ anh sẽ đến thăm đền thờ lần nữa.` (91.33ms)
- [quest_narrative] `Yuna's brother is finally safe, but we had to split up after our escape.`
  -> `Em trai của Yuna cuối cùng cũng an toàn, nhưng chúng tôi đã phải chia tay sau khi trốn thoát.` (96.27ms)
- [quest_narrative] `I should make sure they reached the town of Komatsu Forge.`
  -> `Tôi nên đảm bảo họ đến thị trấn Komatsu Forge.` (44.96ms)
- [quest_narrative] `If Taka has had time to recover, he may be able to make me a tool to climb the walls of Castle Kaneda.`
  -> `Nếu Taka có thời gian hồi phục, anh ấy có thể làm cho tôi một công cụ để leo lên tường của Lâu đài Kaneda.` (95.75ms)
- [quest_narrative] `Find the monk before the bandits reach the bridge.`
  -> `Tìm nhà sư trước khi bọn cướp đến cầu.` (40.58ms)
- [ui_menu] `RESTART FROM LAST CHECKPOINT`
  -> `RỘNG TỪ KIỂM TRA LỚN` (45.53ms)
- [ui_menu] `EXIT TO TITLE SCREEN`
  -> `TẮT TIÊU CHUẨN` (38.91ms)
- [ui_menu] `SAVE GAME`
  -> `TIẾT KIỆM GAME` (31.78ms)
- [ui_menu] `GO TO THE TOWN OF KOMATSU FORGE`
  -> `ĐẾN TÂY DỰNG KOMATSU FORGE` (43.43ms)

### opus-mt-en-vi-ctranslate2

- [subtitle_dialogue] `Masako: We have to go, or we'll lose him.`
  -> `Chúng ta phải đi, nếu không không chúng ta sẽ mất nó.` (93.13ms)
- [subtitle_dialogue] `Do you have news of your family's killers?`
  -> `Anh có tin gì về những kẻ giết gia đình anh không?` (74.76ms)
- [subtitle_dialogue] `Because he is an ungrateful traitor.`
  -> `Bởi vì hắn là kẻ phản bội phản bội, hắn là một kẻ phản phản bội.` (286.84ms)
- [subtitle_dialogue] `After what happened at the inn, I didn't think you'd visit the temple again.`
  -> `Sau chuyện xảy ra ở quán trọ, tôi không nghĩ là anh lại đến thăm đền thờ lần nữa.` (111.53ms)
- [quest_narrative] `Yuna's brother is finally safe, but we had to split up after our escape.`
  -> `Em trai của chị Yun người đã an toàn, nhưng chúng ta phải chia nhau lại sau khi trốn thoát.` (130.29ms)
- [quest_narrative] `I should make sure they reached the town of Komatsu Forge.`
  -> `Tôi phải đảm đảm đảm bảo chắc rằng họ tới thị trấn Kmatttsuttta phải chắc chắc chắc rằng chúng đã tới thị thị trấn Kost an an an chắc chắc là thành phố Kmamamatmats của tỉnh Kmastttthttry Toge.` (326.01ms)
- [quest_narrative] `If Taka has had time to recover, he may be able to make me a tool to climb the walls of Castle Kaneda.`
  -> `Nếu Taka đã có thời gian để hồi phục lại, hắn có thể có thể cho tôi một công cụ để leo được tường thành của thành Castle Kane Kane Kane.` (320.08ms)
- [quest_narrative] `Find the monk before the bandits reach the bridge.`
  -> `Hãy tìm cho tên hòa thượng trước khi bọn cướp đến được cây cầu.` (67.46ms)
- [ui_menu] `RESTART FROM LAST CHECKPOINT`
  -> `K___ ít__ cuối__ qua__A__ ả__ thoát__ khuya__ này__ -__ K_ ít ít_ cuối cuối_ cuối qua_ ít qua_ cuối ;__ khỏi__ tìm__ cho__ muộn__ KDE__ ngươi__L__ lệnh__ trải__ chống__ CHÚ__ nghe__̀__ Tim__ nó__ ,__ Lọc__ sót__ tới__ tránh__ thay__ lời__ mất__ Ủ__ LỜI__ 5__ ;` (647.83ms)
- [ui_menu] `EXIT TO TITLE SCREEN`
  -> `- Để đến cả mấy thằng Steve Steve Steve Buddy Steve Steve, Steve Steve Ted Steve Steve rải rải rải đến đến đến tới đến đến để để đến đến gặp đến đến cả đến đến mấy mấy mấy thằng người Steve Steve nhau Steve Steve cảnh Steve Steve--- Steve Steve nhiều Steve Steve người Steve rải Steve Steve lên Steve Steve 2 Steve Steve bồ rải rải Steve rải-- rải rải- Steve rải đến rải rải nạn rải rải hơn rải rải để để để rải đến tới tới đến rải đến với đến đến qua đến đến rải tới đến tới rải đến để đến tới mấy đến đến bao đến đến nhiều đến đến hơn đến đến với` (585.90ms)
- [ui_menu] `SAVE GAME`
  -> `- Chúng ta chúng ta - - - Chúng - - Quá - - chúng - - Giết - - tiền - - G - - GA - - sĩ - - khuyên - - đổi tiền - tiền tiền tiền - chúng chúng chúng - Giết chúng - chúng! - - Cái - - Tiền - - CỦ - -! - Giết khuyên - chúng khuyên - tiền chúng - tiền! - Chúng chúng - Quá chúng -!` (584.31ms)
- [ui_menu] `GO TO THE TOWN OF KOMATSU FORGE`
  -> `N K K K VÀ K K D K K_ K K khuyên K K CHO K K TRẺ K K CỦ K K NĂM K K phán K K đề K K M K K N K D D D K VÀ D K_ D K D CHO K D VÀ K D phán D K CỦ D K CHO D K khuyên CHO K__ K D_ K_ VÀ K_ CHO K VÀ VÀ K VÀ CHO K khuyên D K NĂM D K M D K TRẺ D K quyết K K K K ĐẾN K K vào K K, K K BẠN K K Ở K K trải K K V K K LÀM K K` (570.01ms)
