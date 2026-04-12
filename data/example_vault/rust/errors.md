# Rust Errors

- map(|&x| x) 这里会把 &str 解成 str，编译器会报 size 在编译时未知。

split_whitespace 返回的是 &str 迭代器。
如果在闭包里把 &str 按值解出来，就会碰到 DST 相关的错误。
