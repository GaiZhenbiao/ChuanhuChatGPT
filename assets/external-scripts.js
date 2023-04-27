
// window.MathJax = {
//     tex: {
//         inlineMath: [['$', '$'], ['\\(', '\\)']]
//     },
//     svg: {
//         fontCache: 'global'
//     }
// };

(function () {
    var script = document.createElement('script');
    script.src = "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/latest.js?config=TeX-MML-AM_CHTML";
    script.async = true;
    document.head.appendChild(script);

    var config = document.createElement("script");
    config.type = "text/x-mathjax-config";
    config.text = "MathJax.Hub.Config({skipStartupTypeset: true, tex2jax: {inlineMath: [['$','$'], ['\\\\(','\\\\)']],displayMath: [['$$','$$'], ['\\\\[','\\\\]']]}});";
    document.head.appendChild(config);
})();
