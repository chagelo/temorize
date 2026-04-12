# Rust Scratch Notes

- String 实现了 Deref，所以可以从 &String 得到 &str。
- str 是 DST，不能像普通定长类型那样直接按值拿出来。
- map(|&x| x) 这里会把 &str 解成 str，编译器会报 size 在编译时未知。

split_whitespace 返回的是 &str 迭代器。
如果在闭包里把 &str 按值解出来，就会碰到 DST 相关的错误。
