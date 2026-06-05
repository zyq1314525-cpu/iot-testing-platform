# main 组件的 CMakeLists.txt
# idf_component_register 告诉构建系统：这个目录下有哪些源文件要编译
idf_component_register(
    SRCS "app_main.c"
    INCLUDE_DIRS "."
)
