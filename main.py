import os
import pandas as pd
from datetime import datetime, time
import pytz
from dotenv import load_dotenv
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update

# Load cấu hình
load_dotenv("cauhinh.env")
TOKEN = os.getenv('TELEGRAM_TOKEN')
SHEET_NAME = os.getenv('SHEET_NAME')
TIMEZONE = pytz.timezone(os.getenv('TIMEZONE'))
REPORT_HOUR, REPORT_MINUTE = map(int, os.getenv('REPORT_TIME').split(':'))

class QuanLyThuChi:
    def __init__(self):
        self.sheet = self._connect_gsheets()

    def _connect_gsheets(self):
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials

        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)
        return client.open(SHEET_NAME).sheet1

    def bao_cao_ngay(self, ngay=None):
        today = datetime.now(TIMEZONE).strftime('%Y-%m-%d') if ngay is None else ngay
        records = self.sheet.get_all_records()
        df = pd.DataFrame(records)
        df['Số tiền'] = pd.to_numeric(df['Số tiền'], errors='coerce').fillna(0).astype(int)
        print("DEBUG TYPES:", df.dtypes)
        print("DEBUG DATA:\n", df)

        if 'Ngay' in df.columns:
            df.rename(columns={'Ngay': 'Ngày'}, inplace=True)

        if 'Ngày' not in df.columns:
            return "Không tìm thấy cột 'Ngày' trong dữ liệu."

        df = df[df['Ngày'] == today]

        if df.empty:
            return None

        tong_thu = df[df['Loại'] == 'Thu']['Số tiền'].sum()
        tong_chi = df[df['Loại'] == 'Chi']['Số tiền'].sum()

        report = f"<b>📊 BÁO CÁO {today}</b>\n"
        report += f"💰 <b>Thu:</b> {tong_thu:,.0f} đ\n"
        report += f"💸 <b>Chi:</b> {tong_chi:,.0f} đ\n"
        report += f"🏦 <b>Còn lại:</b> {tong_thu - tong_chi:,.0f} đ\n\n"
        report += "<b>📉 Chi tiết:</b>\n"

        for idx, row in df.iterrows():
            report += f"- {row['Loại']} {row['Danh mục']}: {row['Số tiền']:,.0f} đ\n"

        return report

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Xin chào! Tôi là bot quản lý thu chi của bạn. Gõ /help để xem hướng dẫn")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 Các lệnh có sẵn:\n"
        "/baocao - Xem báo cáo hôm nay\n"
        "/auto_baocao - Bật báo cáo tự động hàng ngày\n"
        "/stop_baocao - Tắt báo cáo tự động\n"
        "/them [Thu|Chi] [Danh mục] [Số tiền]",
        parse_mode=ParseMode.HTML
    )

async def bao_cao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ql = QuanLyThuChi()
    report = ql.bao_cao_ngay()
    await update.message.reply_text(
        report or "Hôm nay chưa có giao dịch nào",
        parse_mode=ParseMode.HTML
    )

async def gui_bao_cao_tu_dong(context: ContextTypes.DEFAULT_TYPE):
    ql = QuanLyThuChi()
    today = datetime.now(TIMEZONE).strftime('%Y-%m-%d')
    report = ql.bao_cao_ngay(today)
    if report:
        await context.bot.send_message(
            chat_id=context.job.chat_id,
            text=report,
            parse_mode=ParseMode.HTML
        )

async def bat_dau_tu_dong(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    job_queue = context.application.job_queue
    job_queue.run_daily(
        gui_bao_cao_tu_dong,
        time=time(hour=REPORT_HOUR, minute=REPORT_MINUTE),
        days=tuple(range(7)),
        chat_id=chat_id,
        name=str(chat_id)
    )
    await update.message.reply_text(
        f"✅ Đã bật báo cáo tự động lúc {REPORT_HOUR:02d}:{REPORT_MINUTE:02d} hàng ngày",
        parse_mode=ParseMode.HTML
    )

async def dung_tu_dong(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    for job in context.application.job_queue.get_jobs_by_name(str(chat_id)):
        job.schedule_removal()
    await update.message.reply_text(
        "❌ Đã tắt báo cáo tự động",
        parse_mode=ParseMode.HTML
    )

async def them_giao_dich(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        print("🔄 Nhận lệnh /them")
        parts = update.message.text.split(' ', 3)
        if len(parts) < 4:
            await update.message.reply_text("❗ Sai cú pháp. Dùng: /them [Thu|Chi] [Danh mục] [Số tiền]")
            return

        loai, danh_muc, so_tien = parts[1], parts[2], parts[3]
        print(f"➡️ Loại: {loai}, Danh mục: {danh_muc}, Số tiền: {so_tien}")
        ngay = datetime.now(TIMEZONE).strftime('%Y-%m-%d')
        so_tien = int(so_tien.replace(',', ''))

        ql = QuanLyThuChi()
        ql.sheet.append_row([ngay, loai, danh_muc, so_tien])
        print("✅ Ghi thành công vào Google Sheet")
        await update.message.reply_text("✅ Đã lưu giao dịch thành công!")
    except Exception as e:
        print(f"❌ Lỗi khi xử lý /them: {e}")
        await update.message.reply_text(f"❌ Lỗi: {e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print(f"❌ Update {update} caused error {context.error}")

def main():
    application = Application.builder().token(TOKEN).build()

    # Khởi tạo job_queue
    job_queue = application.job_queue

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("baocao", bao_cao))
    application.add_handler(CommandHandler("auto_baocao", bat_dau_tu_dong))
    application.add_handler(CommandHandler("stop_baocao", dung_tu_dong))
    application.add_handler(CommandHandler("them", them_giao_dich))
    application.add_error_handler(error_handler)

    application.run_polling()

if __name__ == '__main__':
    main()
