package com.shiyue.captcha;

import cloud.tianai.captcha.common.constant.CaptchaTypeConstant;
import cloud.tianai.captcha.interceptor.CaptchaInterceptor;
import cloud.tianai.captcha.interceptor.CaptchaInterceptorGroup;
import cloud.tianai.captcha.interceptor.impl.BasicTrackCaptchaInterceptor;
import cloud.tianai.captcha.interceptor.impl.ParamCheckCaptchaInterceptor;
import cloud.tianai.captcha.resource.ResourceStore;
import cloud.tianai.captcha.resource.common.model.dto.Resource;
import cloud.tianai.captcha.resource.impl.LocalMemoryResourceStore;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.servlet.server.ConfigurableServletWebServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.net.InetAddress;
import java.net.UnknownHostException;

@Configuration
class CaptchaConfiguration {
    @Bean
    ResourceStore resourceStore() {
        LocalMemoryResourceStore store = new LocalMemoryResourceStore();
        // Original Tianai animal photo, bundled locally for offline generation.
        store.addResource(CaptchaTypeConstant.ROTATE,
                new Resource("classpath", "captcha/animal-default.jpg", "default"));
        return store;
    }

    @Bean
    CaptchaInterceptor captchaInterceptor() {
        CaptchaInterceptorGroup group = new CaptchaInterceptorGroup();
        group.addInterceptor(new ParamCheckCaptchaInterceptor());
        group.addInterceptor(new BasicTrackCaptchaInterceptor());
        return group;
    }

    @Bean
    WebServerFactoryCustomizer<ConfigurableServletWebServerFactory> loopbackOnly() throws UnknownHostException {
        InetAddress loopback = InetAddress.getByAddress(new byte[]{127, 0, 0, 1});
        return factory -> factory.setAddress(loopback);
    }
}
