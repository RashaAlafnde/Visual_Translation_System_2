import os
import io
import wave
import cv2
import threading
import numpy as np
import sounddevice as sd
import speech_recognition as sr
import customtkinter as ctk
from PIL import Image, ImageTk

# ضبط مظهر الواجهة
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class SignLanguageVideoApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("تطبيق ترجمة الكلام إلى لغة الإشارة (Video Translation)")
        self.geometry("850x700")

        self.is_recording = False
        self.audio_data = []
        self.sample_rate = 16000

        # إعداد مسارات الفيديوهات وسرعة التشغيل
        self.video_folder = "videos"
        self.default_video = os.path.join(self.video_folder, "default.mp4")
        self.playback_speed = 1.5  # يمكنك زيادة أو تقليل السرعة هنا (مثلاً 1.5 يعني أسرع بمرة ونصف)

        self.is_playing_video = False

        # إنشاء المجلد تلقائياً في حال عدم وجوده
        if not os.path.exists(self.video_folder):
            os.makedirs(self.video_folder)

        self.init_ui()

        # تشغيل الفيديو الافتراضي عند فتح البرنامج إن وجد
        if os.path.exists(self.default_video):
            self.play_video_stream(self.default_video, loop=True)

    def init_ui(self):
        # 1. إطار عرض فيديو لغة الإشارة
        self.video_frame = ctk.CTkFrame(self, corner_radius=15, fg_color="#1e272e")
        self.video_frame.pack(pady=15, padx=20, fill="both", expand=True)

        self.video_label = ctk.CTkLabel(
            self.video_frame,
            text="🎥\nمساحة عرض فيديو لغة الإشارة\n(قم بإضافة فيديو default.mp4 وفيديوهات الكلمات والأسماء المركبة داخل مجلد videos)",
            font=("Arial", 16, "bold"),
            text_color="#dcdde1"
        )
        self.video_label.pack(expand=True, fill="both", padx=10, pady=10)

        # 2. إطار عرض النص والنتائج
        self.result_frame = ctk.CTkFrame(self, corner_radius=10)
        self.result_frame.pack(pady=5, padx=20, fill="x")

        self.text_label = ctk.CTkLabel(
            self.result_frame,
            text="النص المنطوق: -",
            font=("Arial", 16),
            anchor="w",
            wraplength=780
        )
        self.text_label.pack(pady=8, padx=15, fill="x")

        self.confidence_label = ctk.CTkLabel(
            self.result_frame,
            text="نسبة الدقة: 0.0%",
            font=("Arial", 14, "bold"),
            text_color="#2ec4b6",
            anchor="w"
        )
        self.confidence_label.pack(pady=4, padx=15, fill="x")

        # 3. زر التسجيل للتحكم الصوتي
        self.mic_button = ctk.CTkButton(
            self,
            text="🎤 بدء التسجيل (تحدث بجملة كاملة)",
            font=("Arial", 15, "bold"),
            fg_color="#27ae60",
            hover_color="#219150",
            height=50,
            command=self.toggle_recording
        )
        self.mic_button.pack(pady=15, padx=20, fill="x")

    def toggle_recording(self):
        if not self.is_recording:
            self.is_recording = True
            self.mic_button.configure(text="⏹️ إيقاف التسجيل ومعالجة الجملة", fg_color="#e74c3c", hover_color="#c0392b")
            self.text_label.configure(text="النص المنطوق: 🔴 جاري الاستماع الآن...")
            self.confidence_label.configure(text="نسبة الدقة: --")

            threading.Thread(target=self.record_audio, daemon=True).start()
        else:
            self.is_recording = False
            self.mic_button.configure(text="⏳ جاري المعالجة وتشغيل الفيديو...", state="disabled")

    def record_audio(self):
        self.audio_data = []

        def callback(indata, frames, time_info, status):
            if self.is_recording:
                self.audio_data.append(indata.copy())

        try:
            with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='int16', callback=callback):
                while self.is_recording:
                    sd.sleep(100)

            if not self.audio_data:
                self.update_results("لم يتم تسجيل أي صوت", 0.0)
                return

            recording = np.concatenate(self.audio_data, axis=0)
            wav_io = io.BytesIO()
            with wave.open(wav_io, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(recording.tobytes())
            wav_io.seek(0)

            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_io) as source:
                audio_content = recognizer.record(source)

            results = recognizer.recognize_google(audio_content, language="ar-SA", show_all=True)

            if results and 'alternative' in results:
                best = results['alternative'][0]
                text = best.get('transcript', '').strip()
                confidence = best.get('confidence', 0.90) * 100
                self.update_results(text, confidence)

                # معالجة النص المنطوق ودعم الأسماء المركبة
                self.process_and_play_sentence(text)
            else:
                self.update_results("لم يتم التعرف على كلام واضح", 0.0)

        except Exception as e:
            self.update_results(f"خطأ: {e}", 0.0)

    def process_and_play_sentence(self, full_text):
        """تحويل الجملة إلى كلمات والبحث عن فيديوهات مركبة أو مفردة متسلسلة"""
        words = [word.strip(".,!؟") for word in full_text.split()]
        video_queue = []

        i = 0
        n = len(words)
        while i < n:
            matched = False
            # محاولة البحث عن اسم مركب من 3 كلمات ثم كلمتين ثم كلمة واحدة
            for length in range(min(3, n - i), 0, -1):
                chunk = "_".join(words[i:i + length])
                chunk_video = os.path.join(self.video_folder, f"{chunk}.mp4")

                if os.path.exists(chunk_video):
                    video_queue.append(chunk_video)
                    i += length
                    matched = True
                    break

            if not matched:
                # إذا لم يتم العثور على ملف مركب، نتخطي الكلمة أو نتعامل معها كفردية إن وجدت
                single_word = words[i]
                single_video = os.path.join(self.video_folder, f"{single_word}.mp4")
                if os.path.exists(single_video):
                    video_queue.append(single_video)
                else:
                    print(f"⚠️ تنبيه: فيديو الكلمة/الاسم المركب ({single_word}) غير موجود")
                i += 1

        if video_queue:
            self.is_playing_video = False
            sd.sleep(50)
            self.is_playing_video = True
            threading.Thread(target=self._play_queue, args=(video_queue,), daemon=True).start()
        elif os.path.exists(self.default_video):
            self.play_video_stream(self.default_video, loop=True)

    def _play_queue(self, queue):
        """تشغيل قائمة الفيديوهات كلمة ورا كلمة بشكل متسلسل وبسرعة مضاعفة"""
        for video_path in queue:
            if not self.is_playing_video:
                break
            self._stream_single_video_sync(video_path)

        # العودة للفيديو الافتراضي الساكن عند انتهاء الفيديوهات
        if os.path.exists(self.default_video) and self.is_playing_video:
            self.play_video_stream(self.default_video, loop=True)

    def _stream_single_video_sync(self, video_path):
        """تشغيل فيديو مفرد أو مركب مع مراعاة سرعة التشغيل المضاعفة"""
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0 or fps > 60:
            fps = 30

        # زيادة معدل الإطارات بناءً على سرعة التشغيل المطلوبة
        frame_time = (1.0 / fps) / self.playback_speed

        while self.is_playing_video and cap.isOpened():
            start_time = cv2.getTickCount()

            ret, frame = cap.read()
            if not ret:
                break  # انتهاء الفيديو الحالي للانتقال للذي يليه مباشرة

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            img = img.resize((500, 350), Image.Resampling.BOX)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(500, 350))

            self.video_label.configure(image=ctk_img, text="")
            self.video_label.image = ctk_img

            end_time = cv2.getTickCount()
            elapsed_time = (end_time - start_time) / cv2.getTickFrequency()

            delay_ms = int((frame_time - elapsed_time) * 1000)
            if delay_ms < 1:
                delay_ms = 1

            cv2.waitKey(delay_ms)

        cap.release()

    def play_video_stream(self, video_path, loop=False):
        self.is_playing_video = False
        sd.sleep(50)
        self.is_playing_video = True
        threading.Thread(target=self._stream_single_video_loop, args=(video_path, loop), daemon=True).start()

    def _stream_single_video_loop(self, video_path, loop):
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0 or fps > 60:
            fps = 30

        frame_time = (1.0 / fps) / self.playback_speed

        while self.is_playing_video and cap.isOpened():
            start_time = cv2.getTickCount()

            ret, frame = cap.read()
            if not ret:
                if loop:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    break

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            img = img.resize((500, 350), Image.Resampling.BOX)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(500, 350))

            self.video_label.configure(image=ctk_img, text="")
            self.video_label.image = ctk_img

            end_time = cv2.getTickCount()
            elapsed_time = (end_time - start_time) / cv2.getTickFrequency()

            delay_ms = int((frame_time - elapsed_time) * 1000)
            if delay_ms < 1:
                delay_ms = 1

            cv2.waitKey(delay_ms)

        cap.release()

    def update_results(self, text, confidence):
        self.text_label.configure(text=f"النص المنطوق: {text}")
        self.confidence_label.configure(text=f"نسبة الدقة: {confidence:.1f}%")

        self.mic_button.configure(
            text="🎤 بدء التسجيل (تحدث بجملة كاملة)",
            fg_color="#27ae60",
            hover_color="#219150",
            state="normal"
        )


if __name__ == "__main__":
    app = SignLanguageVideoApp()
    app.mainloop()