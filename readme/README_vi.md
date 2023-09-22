<div align="right">
  <!-- Language: -->
  <a title="Chinese" href="../README.md">简体中文</a> | English | <a title="Japanese" href="README_ja.md">日本語</a> | <a title="Russian" href="README_ru.md">Russian</a>
</div>

<h1 align="center">川虎 Chat 🐯 Chuanhu Chat</h1>
<div align="center">
  <a href="https://github.com/GaiZhenBiao/ChuanhuChatGPT">
    <img src="https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/70903329/aca3a7ec-4f1d-4667-890c-a6f47bf08f63" alt="Logo" height="156">
  </a>

<p align="center">
    <h3>Giao diện Web nhẹ và thân thiện với người dùng cho LLMs bao gồm ChatGPT/ChatGLM/LLaMA</h3>
    <p align="center">
      <a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/blob/main/LICENSE">
        <img alt="Tests Passing" src="https://img.shields.io/github/license/GaiZhenbiao/ChuanhuChatGPT" />
      </a>
      <a href="https://gradio.app/">
        <img alt="GitHub Contributors" src="https://img.shields.io/badge/Base-Gradio-fb7d1a?style=flat" />
      </a>
      <a href="https://t.me/tkdifferent">
        <img alt="GitHub pull requests" src="https://img.shields.io/badge/Telegram-Nhóm-blue.svg?logo=telegram" />
      </a>
      <p>
        Tương thích với GPT-4 · Chat với tệp · Triển khai cục bộ của LLMs · Tìm kiếm trực tuyến · Đại lý Chuanhu · Tinh chỉnh
      </p>
      <a href="https://www.youtube.com/watch?v=MtxS4XZWbJE"><strong>Hướng dẫn Video</strong></a>
        ·
      <a href="https://www.youtube.com/watch?v=77nw7iimYDE"><strong>Giới thiệu phiên bản 2.0</strong></a>
        ·
      <a href="https://www.youtube.com/watch?v=x-O1jjBqgu4"><strong>Giới thiệu và Hướng dẫn phiên bản 3.0</strong></a>
	||
      <a href="https://huggingface.co/spaces/JohnSmith9982/ChuanhuChatGPT"><strong>Thử nghiệm trực tuyến</strong></a>
      	·
      <a href="https://huggingface.co/login?next=%2Fspaces%2FJohnSmith9982%2FChuanhuChatGPT%3Fduplicate%3Dtrue"><strong>Cài đặt bằng một cú nhấp chuột</strong></a>
    </p>
  </p>
</div>

[![Tiêu đề Video](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/51039745/0eee1598-c2fd-41c6-bda9-7b059a3ce6e7.jpg)](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/51039745/0eee1598-c2fd-41c6-bda9-7b059a3ce6e7?autoplay=1)

## ✨ Cập nhật Phiên bản 5.0!

![Cập nhật ChuanhuChat5](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/70903329/f2c2be3a-ea93-4edf-8221-94eddd4a0178)

<sup>Mới!</sup> Giao diện người dùng hoàn toàn mới! Đẹp đến nỗi nó không giống Gradio, thậm chí còn có hiệu ứng kính mờ!

<sup>Mới!</sup> Đã phù hợp cho thiết bị di động (bao gồm cả điện thoại có viền/lỗ), cấu trúc rõ ràng hơn.

<sup>Mới!</sup> Lịch sử đã được chuyển sang bên trái để sử dụng dễ dàng hơn. Và hỗ trợ tìm kiếm (với biểu thức chính quy), xóa và đổi tên.

<sup>Mới!</sup> Bây giờ bạn có thể để mô hình lớn tự động đặt tên cho lịch sử (Kích hoạt trong cài đặt hoặc tệp cấu hình).

<sup>Mới!</sup> Chuanhu Chat hiện có thể cài đặt như một ứng dụng PWA để trải nghiệm gần native hơn! Hỗ trợ trên Chrome/Edge/Safari v.v.

<sup>Mới!</sup> Biểu tượng đã được phù hợp cho tất cả các nền tảng, trông thoải mái hơn.

<sup>Mới!</sup> Hỗ trợ Tinh chỉnh (fine-tuning) GPT 3.5!

## Các Mô Hình Được Hỗ Trợ

| Các Mô Hình Có Thể Gọi Qua API | Ghi chú | Các Mô Hình Triển Khai Cục Bộ | Ghi chú |
| :---: | --- | :---: | --- |
| [ChatGPT(GPT-4)](https://chat.openai.com) | Hỗ trợ tinh chỉnh gpt-3.5 | [ChatGLM](https://github.com/THUDM/ChatGLM-6B) ([ChatGLM2](https://github.com/THUDM/ChatGLM2-6B)) |
| [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service) |  | [LLaMA](https://github.com/facebookresearch/llama) | Hỗ trợ các mô hình Lora 
| [Google PaLM](https://developers.generativeai.google/products/palm) | Không hỗ trợ phát trực tiếp | [StableLM](https://github.com/Stability-AI/StableLM)
| [iFlytek Starfire Cognition Large Model](https://xinghuo.xfyun.cn) |  | [MOSS](https://github.com/OpenLMLab/MOSS)
| [Inspur Yuan 1.0](https://air.inspur.com/home) |  | 
| [MiniMax](https://api.minimax.chat/) | 
| [XMChat](https://github.com/MILVLG/xmchat) | Không hỗ trợ phát trực tiếp
| [Midjourney](https://www.midjourney.com/) | Không hỗ trợ phát trực tiếp

## Mẹo Sử Dụng

### 💪 Các Chức Năng Mạnh Mẽ
- **Trợ lý Chuanhu**: Tương tự như AutoGPT, tự động giải quyết các vấn đề của bạn;
- **Tìm kiếm trực tuyến**: Dữ liệu của ChatGPT đã quá cũ chưa? Hãy cho LLM cánh của internet;
- **Cơ sở kiến thức**: Hãy để ChatGPT giúp bạn đọc nhanh như ánh sáng về lĩnh vực lượng tử! Trả lời câu hỏi dựa trên các tệp tin.
- **Triển khai LLM cục bộ**: Triển khai bằng một cú nhấp chuột, có ngay một mô hình ngôn ngữ lớn của riêng bạn.

### 🤖 Lời kích hoạt hệ thống
- Lời kích hoạt hệ thống có thể kích hoạt hiệu ứng giả mạo bằng cách thiết lập điều kiện tiên quyết;
- ChuanhuChat cài đặt trước các mẫu lời kích hoạt, nhấp vào `Tải Mẫu Lời Kích Hoạt`, chọn bộ sưu tập mẫu lời kích hoạt trước, sau đó chọn lời kích hoạt bạn muốn trong danh sách bên dưới.

### 💬 Cuộc Trò Chuyện Cơ Bản
- Nếu câu trả lời không thỏa mãn, bạn có thể thử nút `Tạo Lại` hoặc trực tiếp `Xóa vòng trò chuyện này`;
- Ô nhập hỗ trợ xuống dòng, nhấn <kbd>Shift</kbd> + <kbd>Enter</kbd> để xuống dòng;
- Sử dụng các phím mũi tên <kbd>↑</kbd> <kbd>↓</kbd> trong ô nhập để nhanh chóng chuyển đổi giữa các ghi chú đã gửi;
- Tạo cuộc trò chuyện mới mỗi lần quá phiền, hãy thử chức năng `đối thoại đơn`;
- Nút nhỏ bên cạnh bong bóng câu trả lời không chỉ cho phép `sao chép bằng một cú nhấp chuột`, mà còn cho phép bạn `xem văn bản Markdown gốc`;
- Chỉ định ngôn ngữ của câu trả lời, để ChatGPT luôn trả lời bằng một ngôn ngữ cụ thể.

### 📜 Lịch Sử Trò Chuyện
- Lịch sử cuộc trò chuyện sẽ tự động được lưu trữ, bạn không cần phải lo lắng về việc không tìm thấy sau khi hỏi;
- Cách ly lịch sử đa người dùng, chỉ bạn mới có thể thấy chúng;
- Đổi tên cuộc trò chuyện, dễ dàng tìm kiếm trong tương lai;
- <sup>Mới!</sup> Tự động đặt tên cuộc trò chuyện một cách kỳ diệu, để LLM hiểu nội dung cuộc trò chuyện và tự động đặt tên cuộc trò chuyện cho bạn!
- <sup>Mới!</sup> Tìm kiếm cuộc trò chuyện, hỗ trợ biểu thức chính quy!

### 🖼️ Trải Nghiệm Nhỏ và Đẹp
- Chủ đề Tự phát triển Nhỏ và Đẹp, mang lại cho bạn trải nghiệm nhỏ và đẹp;
- Chuyển đổi tự động màu sắc sáng và tối, mang lại cho bạn trải nghiệm thoải mái từ buổi sáng đến buổi tối;
- Hiển thị LaTeX / bảng / khối mã hoàn hảo, hỗ trợ tô màu mã;
- <sup>Mới!</sup> Hoạt hình phi tuyến, hiệu ứng kính mờ, đẹp đến nỗi không giống Gradio!
- <sup>Mới!</sup> Được phù hợp cho Windows / macOS / Linux / iOS / Android, từ biểu tượng đến phù hợp màn hình, mang lại trải nghiệm phù hợp nhất cho bạn!
- <sup>Mới!</sup> Hỗ trợ cài đặt ứng dụng PWA cho trải nghiệm gần native hơn!

### 👨‍💻 Các Chức Năng Geek
- <sup>Mới!</sup> Hỗ trợ Tinh chỉnh gpt-3.5!
- Rất nhiều thông số LLM có sẵn để điều chỉnh;
- Hỗ trợ chuyển đổi máy chủ API;
- Hỗ trợ proxy tùy chỉnh;
- Hỗ trợ cân bằng tải nhiều khóa API.

### ⚒️ Liên Quan Đến Triển Khai
- Triển khai lên máy chủ: Đặt trong `config.json` `"server_name": "0.0.0.0", "server_port": <số cổng của bạn>,`.
- Lấy liên kết công cộng: Đặt trong `config.json` `"share": true,`. Lưu ý rằng chương trình phải đang chạy để truy cập thông qua liên kết công cộng.
- Sử dụng trên Hugging Face: Nên **Nhân bản Không gian** ở góc trên bên phải trước khi sử dụng, phản hồi ứng dụng có thể nhanh hơn.

## Bắt Đầu Nhanh

Thực hiện các lệnh sau trong dòng lệnh:

```shell
git clone https://github.com/GaiZhenbiao/ChuanhuChatGPT.git
cd ChuanhuChatGPT
pip install -r requirements.txt
```

Sau đó, hãy tạo một bản sao của config_example.json, đổi tên thành config.json, và sau đó điền API-Key và các cài đặt khác vào tệp.

```shell
python ChuanhuChatbot.py
```
Cửa sổ trình duyệt sẽ tự động mở, lúc này bạn có thể sử dụng **Chuanhu Chat** để trò chuyện với ChatGPT hoặc các mô hình khác.

> **Lưu ý**
>
>Vui lòng kiểm tra [trang wiki](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程) của chúng tôi để biết hướng dẫn chi tiết.


## Khắc phục sự cố

Khi bạn gặp sự cố, bạn nên thử **tải thủ công các thay đổi mới nhất<sup>1</sup>** and **cập nhật các phụ thuộc<sup>2</sup>** trước, sau đó thử lại. Các bước là:

1. Nhấp vào nút `Tải ZIP` trên trang web, tải mã mới nhất và giải nén để thay thế, hoặc
   ```shell
   git pull https://github.com/GaiZhenbiao/ChuanhuChatGPT.git main -f
   ```
2. Thử cài đặt các phụ thuộc lại (dự án có thể có các phụ thuộc mới)
   ```
   pip install -r requirements.txt
   ```

Thường thì bạn có thể giải quyết hầu hết các vấn đề bằng cách tuân theo các bước này.

Nếu vấn đề vẫn tồn tại, vui lòng tham khảo trang này: [Câu hỏi thường gặp (FAQ)](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/常见问题)

Trang này liệt kê hầu hết tất cả các vấn đề có thể xảy ra và cách giải quyết chúng. Vui lòng đọc kỹ nó.

## Thêm thông tin

Bạn có thể tìm thấy thêm thông tin trong [wiki của chúng tôi](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki):

- [Làm thế nào để đóng góp phiên bản dịch](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/Localization)
- [Làm thế nào để đóng góp](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/贡献指南)
- [Làm thế nào để trích dẫn dự án](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用许可#如何引用该项目)
- [Lịch sử thay đổi dự án](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/更新日志)
- [Giấy phép dự án](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用许可)

## Biểu đồ sao

[![Star History Chart](https://api.star-history.com/svg?repos=GaiZhenbiao/ChuanhuChatGPT&type=Date)](https://star-history.com/#GaiZhenbiao/ChuanhuChatGPT&Date)

## Người đóng góp

<a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=GaiZhenbiao/ChuanhuChatGPT" />
</a>

## Nhà tài trờ

🐯 Nếu bạn thấy dự án này hữu ích, hãy thoải mái mua cho tôi một chai coca hoặc một ly cà phê~

<a href="https://www.buymeacoffee.com/ChuanhuChat" ><img src="https://img.buymeacoffee.com/button-api/?text=Mua cho tôi một ly cà phê&emoji=&slug=ChuanhuChat&button_colour=219d53&font_colour=ffffff&font_family=Poppins&outline_colour=ffffff&coffee_colour=FFDD00" alt="Mua cho tôi một ly cà phê" width="250"></a>

<img width="250" alt="image" src="https://user-images.githubusercontent.com/51039745/226920291-e8ec0b0a-400f-4c20-ac13-dafac0c3aeeb.JPG">

