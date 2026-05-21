Tôi đang làm thuật toán cho dự án IOT, các component, giao thức truyền thông và format payload được ghi cụ thể trong PROTOCOL.md

Cụ thể thuật toán:
Trọng số xe như sau: cars=1, bikes = 0.75
Hệ thống đèn giao thông thông minh sẽ cấp phát cho 2 trục (NS và WE) ( bắc nam và đông tây) thời gian hoạt động. 
ý tưởng của tôi là cấp phát số giây đèn xanh cho mỗi trục tỉ lệ theo lưu lượng xe, trogn mỗi trục sẽ có 4 đèn đỏ (đi thẳng, rẽ trái hướng này và đi thằng, rẽ trái hướng đối diện). tôi sẽ tiêp tục tính tỉ lệ lưu lượng xe 2 hướng để tính ra được thời gian đèn xanh mỗi hướng. Và cần phải chia làm sao để các xe không đan vào nhau. thứ tự sáng sẽ là: x s đầu, đèn trái và thằng bên tôi sáng. Từ giây x đến y. đèn thẳng bên tôi và bên đối diện sáng. Từ giây y đến hết thời gian của trục, đèn trái và thằng bên đối diện sáng. tổng thời gian đèn rẽ trái chiếm 60% tổng thời gian được cấp (coi nó như 1 hyper param)
Lưu ý là để không bias thì tôi sẽ tính tỉ lệ lưu lượng xe lúc tất 4 đèn trong trục đang đỏ. Quy ước hướng (bên tôi) được sáng đèn trái trước trong 1 trục là cố định.

Lấy ví dụ: Giả sử trục đông tây vừa hết lượt đèn xanh. Hiện tại, trục bắc nam đang nhiều xe hơn trục đông tây(lấy dữ liệu xe trục đông tây lúc trước khi xả xe) gấp 4 lần. tôi sẽ cấp cho trục bắc nam 40s,
Giờ ta sẽ cấp đèn cho 4 đèn trong trục này. giả sử hướng bên tôi đông gấp 3 lần hướng bên kia. Tôi tính được tổng thời gian đèn đỏ 2 bên ság là 40*60%=24s. Bên tôi đông gấp 3 nên tính được đỏ trái bên tôi là 18s, bên kia là 6s. đèn đỏ bên kia 6s, ta tính được đèn xanh bên tôi là 40 - 6 = 34s.
Tóm lại: giây thứ nhất đến giây 18, thẳng, trái bên tôi xanh. Giaay 18 đến giây 34, thằng bên tôi và đối diện xanh. Giây 34 đến 40, thẳng trái đối diện xanh.
Hết thời gian, đến lượt trục đông tây, lại lấy lưu lượng xe trục đấy ở giây 40 tính tỉ lệ với lưu lượng xe trục này giây 0
