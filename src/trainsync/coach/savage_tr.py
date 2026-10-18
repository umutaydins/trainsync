"""The savage Turkish pack (BOT_INTENSITY=savage, ADR 0030): original lines, per category.

The owner opted into unrestricted profanity, so the lines swear freely. They roast the excuse or
the effort only: never body, weight or appearance, never identity, never food or eating, never a
push through pain (tests/unit/test_coach_lines.py checks the guardrail blocklist). Lines carry no
numbers: the facts (weights, reps, times) go in a separate line the code writes. No line quotes
or imitates a real person.
"""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

from collections.abc import Mapping

from trainsync.coach.categories import Category
from trainsync.coach.punchlines import PUNCHLINES

LINES: Mapping[Category, tuple[str, ...]] = {
    Category.EXCUSE: (
        "Canın istemiyor mu? Amına koyayım, canının istemesini bekleyen hiçbir şey kaldırmadı.",
        '"Yarın" dediğin gün hiç gelmedi lan. Bugün kalkıyorsun.',
        "Bahane üretmekte şampiyonsun, sikeyim böyle şampiyonluğu.",
        "Bu hafta gitmeyecek misin? Siktir et o cümleyi, çantanı al.",
        "Yorgunum diyorsun; o yorgunluk bahane değil, antrenmanın ta kendisi.",
        "Kafanın içindeki o ses yalan söylüyor ulan, dinleme.",
        "Motivasyon bekleme amk, disiplin kimseyi bekletmez.",
        "Her bahane bir eksik set. Hesabı ben tutuyorum.",
        "Hassiktir, yine aynı hikâye. Değişen tek şey bahanenin kılıfı.",
    ),
    Category.MISSED_WORKOUT: (
        "Bugünkü antrenmanı siktin attın. Yarın iki katı istemiyorum, sadece gel.",
        "Program masada durdu, sen ortada yoktun. Amına koyayım, bu ne?",
        "Salon seni bekledi, sen bahane bekledin.",
        "Kayıt yok, set yok, ter yok. Boş geçen bir gün daha.",
        "Atladığın her antrenman yarınki sana borç. Faizi ağır lan.",
        "Planlı gün geldi geçti. Sen nerdeydin ulan?",
        "Sıfır antrenman. Bahane kabul edilmedi. Yarın ilk iş salon.",
        "Bugün kaçtın. Yarın kaçamazsın, ben buradayım.",
    ),
    Category.UNDER_TARGET: (
        "Hedefin altında kaldın. Siktir et egoyu, sıradaki seti tam yap.",
        "O set yarım kaldı lan. Yarım iş kabul etmiyorum.",
        "Bar sana hükmetti. Sıradakinde sen ona hükmet.",
        "Tekrarlar eksik. Yorgunluk mu, korku mu? İkisinin de amına koyayım.",
        "Program bunu istemedi, daha fazlasını istedi. Kalk, düzelt.",
        "Bu set deftere kötü yazıldı. Sıradakini kurtar.",
        "Eksik tekrar kabul edilmez. Toparla ulan.",
        "Barı bırakmadan önce bir tekrar daha vardı. Biliyorsun.",
    ),
    Category.WORKOUT_START: (
        "Başladık. Telefonu bırak, barı tut.",
        "Antrenman açıldı. Bugün bahane yok, sadece set var.",
        "Hadi lan, ısın ve gömül.",
        "Saat işliyor. Konuşma, kaldır.",
        "En zoru gelmekti, geldin. Şimdi bitir.",
        "Kapıdan girdin, yarısı bitti. Diğer yarısı acıtacak.",
    ),
    Category.REST_OVER: (
        "Kalk, sıradaki set.",
        "Dinlenme bitti amk, bara dön.",
        "Süre doldu. Oturmaya gelmedin.",
        "Kalk ulan, set seni bekliyor.",
        "Nefes aldın, yeter. Kaldır.",
        "Telefonu bırak, sıradaki set.",
        "Mola bitti. Hassiktir, kalk.",
    ),
    Category.WORKOUT_DONE_GOOD: (
        "Tam iş. Bugün bahaneler kaybetti.",
        "Bütün setler yerinde. Aferin lan, yarın yine.",
        "Program tamam. Böyle devam, gevşemek yok.",
        "Hassiktir, temiz iş çıkardın. Dinlen, yemeğini ye, logla.",
        "Bugün söz verdiğini yaptın. Yarın da yap.",
        "Setler tamam, kafa yerinde. Bir sonrakine şimdiden hazırlan.",
    ),
    Category.WORKOUT_DONE_BAD: (
        "Antrenmanı yarım bıraktın. Amına koyayım, eksik setler kendini yapmıyor.",
        "Bitti dedin ama bitmedi. Eksik setler kayıtta duruyor.",
        "Bugün bar kazandı. Bir dahakine sen kazanacaksın, yoksa bırakmam.",
        "Hedefin altında kapattın. Siktir et bugünü, yarın düzelt.",
        "Bu antrenmanın notu: eksik. Bahane yazma, sıradakini tam yap.",
        "Yarım kalan her set bir sonraki antrenmana fatura. Ödeyeceksin.",
    ),
    Category.REMINDER_BEFORE: (
        "30 dakika kaldı. Çantanı hazırla, bahaneyi evde bırak.",
        "Yarım saat sonra antrenman. Su, ayakkabı, kafa: hazır olsun.",
        "30 dakika. Şimdi kalk, yoksa birazdan hiç kalkmayacaksın.",
        "Saat yaklaşıyor amk. Hazırlan.",
        "Yarım saat sonra sahne senin. Kafayı şimdiden ısıt.",
    ),
    Category.REMINDER_NOW: (
        "Saat geldi. Başla.",
        "Şimdi. Ne yarın, ne sonra. Şimdi.",
        "Antrenman saati ulan. Kalk.",
        "Zamanı geldi. Bahaneler sonra konuşur, önce sen kaldır.",
        "Başlama saati. Telefonu kapat, salona git.",
    ),
    Category.ESCALATION: (
        "Yarım saat geçti, hâlâ başlamadın. Amına koyayım, kalk.",
        "Hâlâ yok musun? Program bekliyor, ben bekliyorum, sen bahane arıyorsun.",
        "Bugünü kurtarmak için hâlâ vakit var. Siktir et beklemeyi.",
        "Kanepe kazanıyor şu an. Kaybetmeye alışma.",
        "Başlamadın. 20 dakika bile yeter, ama şimdi.",
        "Hassiktir, hâlâ hareket yok. Ayakkabıları giy, gerisi gelir.",
    ),
    Category.LANGUAGE_SET: (
        "Tamam, Türkçe. Dil değişti, bahanelerin aynı kaldı mı bakacağız.",
        "Türkçe tamam. Artık anlamadım deme şansın da yok amk.",
        "Dil Türkçe oldu. Şimdi kalk ve aynı dilde terle.",
        "Ana dilinde ayar yiyeceksin artık. Hazır ol.",
        "Türkçeye geçtik. Bahane de Türkçe olsa sökmez, haberin olsun.",
    ),
    Category.PUNCHLINE_EN: PUNCHLINES,
}
