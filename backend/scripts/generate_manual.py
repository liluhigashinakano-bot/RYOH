"""POSSYS 利用マニュアル PDF生成スクリプト（スクリーンショット付き）"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop", "POSSYS_manual.pdf")
IMG_DIR = os.path.join(BASE_DIR, "data", "manual_images", "cropped")
W, H = A4
MARGIN = 15 * mm
CONTENT_W = W - 2 * MARGIN
DARK = HexColor("#1a1a2e")
PRIMARY = HexColor("#7c3aed")
GRAY = HexColor("#555555")
BLACK = HexColor("#000000")
WHITE = HexColor("#ffffff")


def img_path(num):
    return os.path.join(IMG_DIR, f"{num:02d}.png")


def draw_cover(c):
    c.setFillColor(DARK)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(PRIMARY)
    c.rect(0, H / 2 - 2 * mm, W, 4 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("HeiseiKakuGo-W5", 36)
    c.drawCentredString(W / 2, H / 2 + 30 * mm, "POSSYS")
    c.setFont("HeiseiKakuGo-W5", 14)
    c.drawCentredString(W / 2, H / 2 + 12 * mm, "業務管理システム 利用マニュアル")
    c.setFont("HeiseiKakuGo-W5", 10)
    c.drawCentredString(W / 2, H / 2 - 20 * mm, "2026年4月版")
    c.showPage()


class DocWriter:
    def __init__(self, c):
        self.c = c
        self.y = H - MARGIN
        self.page = 1

    def _check_page(self, need=15 * mm):
        if self.y < MARGIN + need:
            self._footer()
            self.c.showPage()
            self.page += 1
            self.y = H - MARGIN
            self._header()

    def _header(self):
        self.c.setStrokeColor(PRIMARY)
        self.c.setLineWidth(0.5)
        self.c.line(MARGIN, H - MARGIN + 4 * mm, W - MARGIN, H - MARGIN + 4 * mm)
        self.c.setFillColor(GRAY)
        self.c.setFont("HeiseiKakuGo-W5", 6.5)
        self.c.drawString(MARGIN, H - MARGIN + 5.5 * mm, "POSSYS 利用マニュアル")

    def _footer(self):
        self.c.setFillColor(GRAY)
        self.c.setFont("HeiseiKakuGo-W5", 7)
        self.c.drawCentredString(W / 2, 8 * mm, f"- {self.page} -")

    def page_break(self):
        self._footer()
        self.c.showPage()
        self.page += 1
        self.y = H - MARGIN
        self._header()

    def chapter(self, num, title):
        self.page_break()
        self.c.setFillColor(PRIMARY)
        self.c.rect(MARGIN, self.y - 2 * mm, CONTENT_W, 9 * mm, fill=1, stroke=0)
        self.c.setFillColor(WHITE)
        self.c.setFont("HeiseiKakuGo-W5", 13)
        self.c.drawString(MARGIN + 4 * mm, self.y, f"第{num}章  {title}")
        self.y -= 15 * mm

    def section(self, title, ensure=40 * mm):
        self._check_page(ensure)
        self.c.setFillColor(PRIMARY)
        self.c.rect(MARGIN, self.y + 1 * mm, 2.5 * mm, 4.5 * mm, fill=1, stroke=0)
        self.c.setFillColor(BLACK)
        self.c.setFont("HeiseiKakuGo-W5", 10)
        self.c.drawString(MARGIN + 5 * mm, self.y, title)
        self.y -= 8 * mm

    def body(self, text):
        self.c.setFillColor(BLACK)
        self.c.setFont("HeiseiMin-W3", 8.5)
        for line in text.split("\n"):
            while len(line) > 0:
                self._check_page()
                chunk = line[:60]
                line = line[60:]
                self.c.drawString(MARGIN + 4 * mm, self.y, chunk)
                self.y -= 4.5 * mm

    def bullet(self, text):
        self._check_page()
        self.c.setFillColor(BLACK)
        self.c.setFont("HeiseiMin-W3", 8.5)
        self.c.drawString(MARGIN + 4 * mm, self.y, f"・{text}")
        self.y -= 4.5 * mm

    def spacer(self, h=3):
        self.y -= h * mm

    def image(self, num, caption=None, max_h=35 * mm):
        p = img_path(num)
        if not os.path.exists(p):
            return
        try:
            img = ImageReader(p)
            iw, ih = img.getSize()
            scale = CONTENT_W / iw
            draw_w = CONTENT_W
            draw_h = ih * scale
            if draw_h > max_h:
                scale2 = max_h / draw_h
                draw_w *= scale2
                draw_h = max_h
            self._check_page(draw_h + 10 * mm)
            x = MARGIN + (CONTENT_W - draw_w) / 2
            self.c.setStrokeColor(HexColor("#cccccc"))
            self.c.setLineWidth(0.4)
            self.c.rect(x - 0.5, self.y - draw_h - 0.5, draw_w + 1, draw_h + 1, fill=0, stroke=1)
            self.c.drawImage(p, x, self.y - draw_h, draw_w, draw_h, preserveAspectRatio=True, anchor='c')
            self.y -= draw_h + 2 * mm
            if caption:
                self.c.setFillColor(GRAY)
                self.c.setFont("HeiseiKakuGo-W5", 6.5)
                self.c.drawCentredString(W / 2, self.y, caption)
                self.y -= 5 * mm
            else:
                self.y -= 2 * mm
        except Exception as e:
            print(f"  Warning: image {num}: {e}")

    def images_row(self, nums, captions=None, max_h=32 * mm):
        valid = [(n, img_path(n)) for n in nums if os.path.exists(img_path(n))]
        if not valid:
            return
        count = len(valid)
        gap = 2 * mm
        cell_w = (CONTENT_W - gap * (count - 1)) / count
        max_draw_h = 0
        for _, p in valid:
            img = ImageReader(p)
            iw, ih = img.getSize()
            dh = min(ih * (cell_w / iw), max_h)
            if dh > max_draw_h:
                max_draw_h = dh
        self._check_page(max_draw_h + 12 * mm)
        for i, (num, p) in enumerate(valid):
            img = ImageReader(p)
            iw, ih = img.getSize()
            scale = cell_w / iw
            draw_w = cell_w
            draw_h = ih * scale
            if draw_h > max_h:
                s2 = max_h / draw_h
                draw_w *= s2
                draw_h = max_h
            x = MARGIN + i * (cell_w + gap) + (cell_w - draw_w) / 2
            self.c.setStrokeColor(HexColor("#cccccc"))
            self.c.setLineWidth(0.3)
            self.c.rect(x - 0.5, self.y - max_draw_h - 0.5, draw_w + 1, draw_h + 1, fill=0, stroke=1)
            self.c.drawImage(p, x, self.y - max_draw_h + (max_draw_h - draw_h), draw_w, draw_h, preserveAspectRatio=True, anchor='c')
        self.y -= max_draw_h + 2 * mm
        if captions:
            for i, cap in enumerate(captions[:count]):
                x = MARGIN + i * (cell_w + gap) + cell_w / 2
                self.c.setFillColor(GRAY)
                self.c.setFont("HeiseiKakuGo-W5", 6)
                self.c.drawCentredString(x, self.y, cap)
            self.y -= 5 * mm
        else:
            self.y -= 2 * mm

    def finalize(self):
        self._footer()
        self.c.showPage()


def build_manual():
    c = canvas.Canvas(OUTPUT, pagesize=A4)
    c.setTitle("POSSYS 利用マニュアル")
    c.setAuthor("POSSYS")
    draw_cover(c)
    d = DocWriter(c)
    d._header()

    # 目次
    d.c.setFillColor(BLACK)
    d.c.setFont("HeiseiKakuGo-W5", 14)
    d.c.drawCentredString(W / 2, d.y, "目 次")
    d.y -= 12 * mm
    for i, t in enumerate(["ログイン・権限について","リアルタイム情報","POS・伝票","顧客管理","従業員管理","月次レポート","アカウント管理","メニュー管理","設定"], 1):
        d.c.setFont("HeiseiKakuGo-W5", 10)
        d.c.setFillColor(BLACK)
        d.c.drawString(MARGIN + 10 * mm, d.y, f"第{i}章  {t}")
        d.y -= 7 * mm
    d._footer(); d.c.showPage(); d.page += 1; d.y = H - MARGIN; d._header()

    # 第1章
    d.chapter(1, "ログイン・権限について")
    d.section("ログイン方法")
    d.body("ブラウザでPOSSYSのURLにアクセスし、メールアドレスとパスワードを入力します。")
    d.spacer()
    d.section("ユーザー権限（ロール）")
    d.body("ユーザーには以下の権限があり、利用できる機能が異なります。")
    d.bullet("管理者（Administrator）：全機能にアクセス可能")
    d.bullet("マネージャー（Manager）：管理者に準ずる権限")
    d.bullet("編集者（Editor）：データの閲覧・編集が可能")
    d.bullet("従業員（Staff）：基本的な業務操作が可能")
    d.bullet("オーダー端末：POS機能のみ利用可能")
    d.bullet("キャスト：限定的な閲覧権限")
    d.bullet("閲覧のみ（Read-only）：データの閲覧のみ")
    d.spacer()
    d.body("各ユーザーにはページごとに「閲覧」「編集」権限を個別設定できます。")

    # 第2章
    d.chapter(2, "リアルタイム情報")
    d.section("概要", ensure=60 * mm)
    d.body("全店舗の営業状況をリアルタイムで一覧表示するトップページです。")
    d.image(1, "リアルタイム情報 - 店舗一覧・売上・天気情報")
    d.section("表示内容", ensure=60 * mm)
    d.bullet("各店舗の売上合計（会計済み＋未会計）・来店組数・人数")
    d.bullet("出勤中のキャスト・スタッフ一覧")
    d.bullet("ドリンク売上・シャンパン売上・当月ランキング")
    d.bullet("誕生日アラート・天気/交通情報")
    d.image(2, "店舗別の売上詳細・天気情報・出勤キャスト")

    # 第3章
    d.chapter(3, "POS・伝票")
    d.section("伝票一覧", ensure=55 * mm)
    d.body("オープン中の伝票がカード形式で表示されます。")
    d.image(26, "POS画面 - オープン中の伝票一覧")
    d.section("伝票の詳細画面", ensure=55 * mm)
    d.body("伝票をタップすると詳細が開きます（テーブル・タイマー・注文・合計）。")
    d.image(3, "伝票詳細画面 - B1卓")
    d.section("注文の入力", ensure=55 * mm)
    d.body("右側メニューから注文を追加します。")
    d.image(4, "注文入力 - ドリンクメニュー一覧")
    d.bullet("Sドリンク / Lドリンク / MGドリンク / シャンパン / ショット 等")
    d.section("数量の変更", ensure=50 * mm)
    d.body("注文済みの項目をタップすると数量を変更できます。")
    d.images_row([19, 20, 21], ["メニュー展開中", "延長行ハイライト", "数量変更入力"])
    d.section("キャスト選択（ドリンク注文時）", ensure=50 * mm)
    d.body("ドリンク注文時に対象キャストを選択。ドリンクバックに反映されます。")
    d.images_row([5, 6], ["Lドリンク - キャスト選択", "シャンパン - キャスト按分設定"])
    d.section("顧客・キャストの紐付け", ensure=50 * mm)
    d.body("伝票に顧客情報や担当キャストを紐付けできます。")
    d.images_row([16, 17, 18], ["顧客選択", "担当キャスト設定", "対応中キャスト設定"])
    d.section("合流追加", ensure=50 * mm)
    d.body("途中から人数が増えた場合、N/R区分とプランを指定して追加します。")
    d.image(22, "合流追加モーダル")
    d.section("概算伝票・領収書", ensure=50 * mm)
    d.body("概算伝票：お客様に提示する明細書。領収書：宛名・但し書き指定可。")
    d.images_row([23, 24, 25], ["概算伝票PDF", "領収書発行画面", "領収書PDF"])
    d.section("合算・先会計・割り勘", ensure=55 * mm)
    d.images_row([11, 12, 13], ["合算 - 伝票選択", "先会計", "割り勘"])
    d.bullet("合算：複数伝票を1つに / 先会計：一部先精算 / 割り勘：分割精算")
    d.section("合計修正・伝票削除・先退店", ensure=55 * mm)
    d.images_row([7, 8, 9], ["合計修正（値引き/加算）", "伝票削除", "先退店"])
    d.bullet("合計修正：端数カット等 / 削除：理由必須 / 先退店：途中退店記録")
    d.section("操作ログ・タイマー", ensure=50 * mm)
    d.body("伝票の操作履歴確認、タイマー一時停止が可能です。")
    d.images_row([14, 15], ["操作ログ", "セットタイマー一時停止"])
    d.section("接客メモ", ensure=55 * mm)
    d.body("伝票ごとにメモを登録。顧客詳細に来店日ごとに表示されます。")
    d.image(38, "接客メモの登録画面")
    d.section("ティッシュ配り管理", ensure=50 * mm)
    d.body("キャストのティッシュ配り状況を管理します。")
    d.images_row([47, 27], ["ティッシュ配り開始", "配り状況一覧"])
    d.section("勤怠管理", ensure=55 * mm)
    d.body("社員・アルバイト・キャストの出退勤を管理します。")
    d.image(28, "勤怠管理画面")
    d.section("出勤登録（3タイプ）", ensure=50 * mm)
    d.images_row([33, 34, 35], ["通常出勤", "ヘルプ出勤", "体験入店"])
    d.section("退勤・勤怠削除・社員登録", ensure=50 * mm)
    d.images_row([29, 30, 31], ["退勤時間選択", "退勤確定後", "勤怠削除"])
    d.spacer()
    d.image(32, "社員/アルバイト出勤登録")
    d.section("会計済み伝票", ensure=50 * mm)
    d.body("会計済みの伝票履歴を日付範囲で絞り込み確認できます。")
    d.images_row([36, 37], ["会計済み伝票一覧", "会計済み伝票詳細"])
    d.section("操作ログ一覧", ensure=55 * mm)
    d.body("当日の全操作ログを時系列で確認できます。")
    d.image(39, "営業操作ログ一覧")
    d.section("日報", ensure=55 * mm)
    d.body("営業日ごとの売上・実績サマリーです。")
    d.image(40, "日報 - 日付別売上と詳細")
    d.section("日報の詳細内容", ensure=50 * mm)
    d.images_row([41, 42], ["ティッシュ・コース内訳", "キャスト分析"])
    d.spacer()
    d.images_row([43, 44, 45], ["社員実績", "天気・集客情報", "日別売上"])
    d.section("営業締め", ensure=55 * mm)
    d.body("営業終了時に釣銭残高・出金記録を入力して売上を確定します。")
    d.image(46, "営業締め画面")

    # 第4章
    d.chapter(4, "顧客管理")
    d.section("顧客一覧", ensure=55 * mm)
    d.body("全顧客を一覧表示。店舗絞り込み・名前検索・13項目で並び替え可能。")
    d.image(48, "顧客一覧画面")
    d.section("顧客詳細 — 基本情報", ensure=55 * mm)
    d.body("来店回数・累計売上・平均売上・滞在時間などの統計を表示。")
    d.image(49, "顧客詳細 - 基本情報")
    d.section("顧客詳細 — セット傾向・来店曜日", ensure=55 * mm)
    d.body("ドリンク傾向・来店曜日分布・来店動機・AIカルテを表示。")
    d.image(50, "セット傾向・来店曜日・来店動機")
    d.section("メモ・来店履歴・キャスト実績", ensure=50 * mm)
    d.images_row([51, 52, 53], ["メモタブ", "来店履歴タブ", "キャスト実績タブ"])
    d.bullet("メモ：接客メモ追加・AI分析 / 来店履歴 / キャスト別実績")

    # 第5章
    d.chapter(5, "従業員管理")
    d.section("キャスト一覧", ensure=55 * mm)
    d.body("店舗ごとのキャスト一覧。15指標で並び替え可能。")
    d.image(54, "キャスト一覧")
    d.section("キャスト詳細 — 基本情報", ensure=55 * mm)
    d.body("キャストID・源氏名・ランク・時給・お酒の強さ等。")
    d.image(55, "基本情報")
    d.section("キャスト詳細 — 統計", ensure=55 * mm)
    d.body("実質時給・出勤数・ドリンク実績・シャンパンバック等。")
    d.image(56, "統計データ")
    d.section("キャスト詳細 — 出勤履歴", ensure=55 * mm)
    d.body("日ごとの実勤務時間・日給・遅刻マークを表示。")
    d.image(57, "出勤履歴")

    # 第6章
    d.chapter(6, "月次レポート")
    d.section("月次サマリー", ensure=55 * mm)
    d.body("店舗ごとの月間売上・来店数・客単価を集計表示。")
    d.image(58, "月次サマリー")
    d.section("ドリンク・シャンパン・人件費", ensure=55 * mm)
    d.image(59, "ドリンク・シャンパン・人件費")
    d.section("キャスト別実績", ensure=50 * mm)
    d.body("キャスト別の出勤日数・売上貢献・ドリンク実績。")
    d.images_row([60, 62], ["キャスト実績", "キャスト実績（続き）"])
    d.section("社員実績・日別売上", ensure=55 * mm)
    d.image(61, "社員実績・日別売上")

    # 第7章
    d.chapter(7, "アカウント管理")
    d.section("権限管理（アカウント別）", ensure=55 * mm)
    d.body("ユーザーごとに各ページの閲覧・編集権限を設定。")
    d.image(63, "権限管理 - アカウント別")
    d.section("権限管理（グループ別）", ensure=55 * mm)
    d.body("ロール単位で権限テンプレートを設定。新規ユーザーに自動適用。")
    d.image(64, "権限管理 - グループ別")
    d.section("店舗管理", ensure=55 * mm)
    d.body("店舗の追加・編集（店舗名・営業時間・料金・領収書設定等）。")
    d.image(65, "店舗管理画面")

    # 第8章
    d.chapter(8, "メニュー管理")
    d.section("追加注文メニュー", ensure=55 * mm)
    d.body("店舗ごとのカスタムメニュー項目を管理します。")
    d.image(66, "追加注文メニュー一覧")
    d.section("メニュー追加", ensure=55 * mm)
    d.body("メニュー名・単価・キャスト選択要否・インセンティブを設定。")
    d.image(68, "メニュー追加モーダル")
    d.section("インセンティブ設定", ensure=55 * mm)
    d.body("キャストのドリンクインセンティブ率（L/MG/S/ショット/シャンパン等）。")
    d.image(67, "インセンティブ率設定")

    # 第9章
    d.chapter(9, "設定")
    d.section("店舗別設定", ensure=55 * mm)
    d.body("店舗ごとに以下の設定を切り替えられます。")
    d.image(69, "設定画面")
    d.bullet("AI付け回しエージェント：キャストの付け回しをAIが提案")
    d.bullet("伝票開始ボタン：手動/自動セット開始の切り替え")

    d.finalize()
    c.save()
    print(f"PDF generated: {os.path.abspath(OUTPUT)}")


if __name__ == "__main__":
    build_manual()
