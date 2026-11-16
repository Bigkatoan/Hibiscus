# Hibiscus Station

Hibiscus Station, ứng dụng chạy trên máy tính cắm robot (kết nối và hiệu chỉnh tay robot, camera,
teleop, thu dataset, upload, tải model đã train về và chạy với telemetry động cơ, tự dừng khi quá
nhiệt, cùng quỹ đạo, chương trình khối và bản sao 3D), nay nằm ở repository riêng:

**<https://github.com/Bigkatoan/hibiscus-station>**

Hướng dẫn sử dụng, danh sách nghiệm thu trên phần cứng, đặc tả và cách cài đặt đều ở đó.

Phía server không thay đổi gì: Station upload dataset qua cùng cơ chế upload tiếp tục được như
`hibiscus push` ([Dataset](02-dataset.md)), tải model bundle như `hibiscus pull`
([Chạy trên robot](06-chay-tren-robot.md)) và xác thực bằng personal access token. Sau khi cài
Station, `hibiscus station …` sẽ mở nó ([CLI trên máy collect](03-cli-may-collect.md)).
