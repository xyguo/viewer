# <span class="segment" data-seg="BSG-p001-0001">Balog-Szemerédi-Gowers Theorem</span>

<span class="segment" data-seg="BSG-p001-0002">清水 伸高*</span>

<span class="segment" data-seg="BSG-p001-0003">April 29, 2022</span>

## <span class="segment" data-seg="BSG-p001-0004">Abstract</span>

<span class="segment" data-seg="BSG-p001-0005">アーベル群 $A,B$ から一つずつ要素を選んだ時の和を考える.</span> <span class="segment" data-seg="BSG-p001-0006">この和のほとんどがある小さい集合に属する時に $A,B$ が満たす構造的性質を捉えたのが Balog-Szemerédi-Gowers の定理である.</span> <span class="segment" data-seg="BSG-p001-0007">本稿ではこの定理を紹介し証明する.</span>

# <span class="segment" data-seg="BSG-p001-0008">1 Balog-Szemerédi-Gowers Theorem (BSG Theorem)</span>

<span class="segment" data-seg="BSG-p001-0009">アーベル群 $G$ の二つの部分集合 $A,B\subseteq G$ に対して $A+B:=\{a+b:a\in A,b\in B\}$ のサイズは一般に $|A||B|$ まで大きくなりうるが, どのような条件の下で小さくなるだろうか?</span> <span class="segment" data-seg="BSG-p001-0010">直感的には, $A+B$ が小さいということは $c\in A+B$ に対して $c=a+b$ を満たす $a\in A,b\in B$ の選び方がたくさんあれば $A+B$ は小さくなることが期待される.</span> <span class="segment" data-seg="BSG-p001-0011">即ち, 多くの組 $(a,b)\in A\times B$ に対しその和 $a+b$ がある小さい集合 $C\subseteq G$ に含まれているならば $|A+B|$ は小さくなるだろうか?</span> <span class="segment" data-seg="BSG-p001-0012">残念ながら反例が存在する.</span>

<span class="segment" data-seg="BSG-p001-0013">例として $V\subseteq\mathbb{F}_2^n$ を $\dim V=d$ なる部分空間, $R\subseteq\mathbb{F}_2^n$ を $2^d$ 個のランダムなベクトルからなる集合とし, $A=B=V\cup R$ とする.</span> <span class="segment" data-seg="BSG-p001-0014">ランダムに $a\sim A,b\sim B$ をとってくると確率 $1/4$ で $a,b\in V$ となり, $a+b\in V$ である.</span> <span class="segment" data-seg="BSG-p001-0015">つまり $(a,b)$ のうち $25\%$ はその和が $V$ に属する.</span> <span class="segment" data-seg="BSG-p001-0016">一方で $d$ が小さければ高確率で $V\cup R$ は次元 $2d$ の部分空間を張り, $|A+B|=|\operatorname{span}(V\cup R)|=2^{2d}=|A||B|$ となってしまう.</span>

<span class="segment" data-seg="BSG-p001-0017">BSG 定理は同様の条件を満たす $A,B$ に対して密な部分集合 $A'\subseteq A,B'\subseteq B$ をうまく選んで $|A'+B'|$ を小さくできることを主張する.</span> <span class="segment" data-seg="BSG-p001-0018">BSG 定理は Balog and Szemerédi [BS94] が最初に証明し, その後 Gowers [Gow98] によってより単純な証明が与えられた.</span>

**<span class="segment" data-seg="BSG-p001-0019">Theorem 1.1 (BSG theorem [BS94; Gow98]).</span>** <span class="segment" data-seg="BSG-p001-0020">$G$ をアーベル群とし, $A,B\subseteq G$ を $|A|=|B|=N$ とする.</span> <span class="segment" data-seg="BSG-p001-0021">サイズ $|C|=cN$ のある $C\subseteq G$ が存在して $\Pr_{a\sim A,b\sim B}[a+b\in C]\geq\epsilon$ を満たすとする.</span> <span class="segment" data-seg="BSG-p001-0022">この時, $|A'|,|B'|\geq(\epsilon^2/16)N$ を満たすある $A'\subseteq A,B'\subseteq B$ が存在して $|A'+B'|\leq 2^{12}c^3(1/\epsilon)^5N$ を満たす.</span>

<span class="segment" data-seg="BSG-p001-0023">本稿では Sudakov, Szemerédi, and Vu [SSV05] による証明を紹介する.</span> <span class="segment" data-seg="BSG-p001-0024">Lovett [Lov17] のサーベイ論文でも同じ証明が紹介されているが, 本稿の証明では以下で示す逆マルコフの不等式などを用いて行間を小さくしている.</span>

# <span class="segment" data-seg="BSG-p001-0025">2 準備</span>

<span class="segment" data-seg="BSG-p001-0026">有限集合 $S$ 上一様ランダムに要素 $x$ が選ばれるとき, $x\sim S$ と表す.</span>

<span class="segment" data-seg="BSG-p001-0027">有限集合 $V$ と $E\subseteq\binom{V}{2}$ に対して $G=(V,E)$ をグラフという.</span> <span class="segment" data-seg="BSG-p001-0028">$V$ を頂点集合と呼び, その要素を頂点と呼ぶ.</span> <span class="segment" data-seg="BSG-p001-0029">$E$ を辺集合と呼び, その要素を辺と呼ぶ.</span> <span class="segment" data-seg="BSG-p001-0030">二つの頂点 $u,v\in V$ は $\{u,v\}\in E$ を満たすとき, 隣接しているという.</span> <span class="segment" data-seg="BSG-p001-0031">しばしば辺 $\{u,v\}$ を $uv$ と略記する.</span> <span class="segment" data-seg="BSG-p001-0032">頂点 $v$ に対し, $v$ と隣接する頂点の集合を $N(v)$ で表し, その要素数を次数と呼び $\deg(v)$ と表す.</span> <span class="segment" data-seg="BSG-p001-0033">すなわち $N(v)=\{u\in V:uv\in E\}$ 及び $\deg(v)=|N(v)|$ である.</span>

<span class="segment" data-seg="BSG-p001-0034">* Tokyo Institute of Technology Email: shimizu.n.ah@m.titech.ac.jp</span>

<span class="segment" data-seg="BSG-p002-0001">頂点列 $(v_1,\ldots,v_k)$ であって全ての $i\in\{1,\ldots,k-1\}$ に対し $v_iv_{i+1}\in E$ を満たすものをウォーク (または路) と呼び, 始点 $v_1$ と終点 $v_k$ を指定する場合は $v_1v_k$-ウォークと呼ぶ.</span> <span class="segment" data-seg="BSG-p002-0002">ウォーク $(v_1,\ldots,v_k)$ の長さを $k-1$ で定義する.</span> <span class="segment" data-seg="BSG-p002-0003">特に全ての $v_1,\ldots,v_k$ が相異なるときはパスと呼ぶ.</span> <span class="segment" data-seg="BSG-p002-0004">$v_1=v_k$ を満たすウォークを閉じたウォークといい, $v_1,\ldots,v_{k-1}$ が相異なる閉じたウォークを閉路 (またはサイクル) と呼ぶ.</span> <span class="segment" data-seg="BSG-p002-0005">二つの有限集合 $A,B$ 及び $E\subseteq A\times B$ の三つ組 $(A,B,E)$ を二部グラフと呼ぶ.</span> <span class="segment" data-seg="BSG-p002-0006">二部グラフはグラフ $(A\cup B,E)$ と同一視することによって $N(v)$ やウォークなどを定義する.</span>

**<span class="segment" data-seg="BSG-p002-0007">Lemma 2.1 (Markov の不等式).</span>** <span class="segment" data-seg="BSG-p002-0008">非負値をとる確率変数 $X$ が $\mathbb{E}[X]<\infty$ であるとき, 任意の $a>0$ に対し $\Pr[X\geq a]\leq\mathbb{E}[X]/a$.</span>

**<span class="segment" data-seg="BSG-p002-0009">Lemma 2.2 (逆 Markov の不等式).</span>** <span class="segment" data-seg="BSG-p002-0010">$[0,1]$ に値をとる確率変数を $X$ とし, $\mu:=\mathbb{E}[X]\in(0,1)$ とする.</span> <span class="segment" data-seg="BSG-p002-0011">このとき, $\Pr[X\geq\mu/2]\geq\mu/2$ が成り立つ.</span>

*<span class="segment" data-seg="BSG-p002-0012">Proof.</span>* <span class="segment" data-seg="BSG-p002-0013">Markov の不等式より, 任意の $c\in(0,1)$ に対して</span>

$$
\begin{aligned}
\Pr[X\leq c]
  &=\Pr[1-X\geq1-c]\\
  &\leq\frac{1-\mu}{1-c}\\
  &=1-\frac{\mu-c}{1-c}\\
  &\leq1-(\mu-c).
\end{aligned}
$$

<span class="segment" data-seg="BSG-p002-0014">$c=\mu/2$ を代入すればよい.</span>

**<span class="segment" data-seg="BSG-p002-0015">Lemma 2.3.</span>** <span class="segment" data-seg="BSG-p002-0016">グラフ $G=(V,E)$ とパラメータ $c$ に対し, $H=\{v\in V:\deg(v)\geq c\}$ 及び $L=V\setminus H$ とする.</span> <span class="segment" data-seg="BSG-p002-0017">このとき, $|H|\leq 2|E|/c$ および $|L|=|V|-|H|\geq|V|-2|E|/c$ が成り立つ.</span>

*<span class="segment" data-seg="BSG-p002-0018">Proof.</span>* <span class="segment" data-seg="BSG-p002-0019">ランダムな頂点 $v\sim V$ に対し $\mathbb{E}[\deg(v)]=2|E|/|V|$ である.</span> <span class="segment" data-seg="BSG-p002-0020">Markov の不等式 (Lemma 2.1) より $|H|/|V|=\Pr[\deg(v)\geq c]\leq 2|E|/(c|V|)$ を得る.</span>

# <span class="segment" data-seg="BSG-p002-0021">3 証明</span>

<span class="segment" data-seg="BSG-p002-0022">まずグラフに関する以下の補題を証明する.</span>

**<span class="segment" data-seg="BSG-p002-0023">Lemma 3.1 ([SSV05]).</span>** <span class="segment" data-seg="BSG-p002-0024">$H=(A,B,E)$ を二部グラフで $|A|=|B|=N$, 辺集合 $E\subseteq A\times B$ が $|E|=\epsilon N^2$ を満たすとする.</span> <span class="segment" data-seg="BSG-p002-0025">このとき, $|A'|,|B'|\geq(\epsilon^2/16)N$ を満たすある $A'\subseteq A,B'\subseteq B$ であって, 任意の $a\in A',b\in B'$ に対して長さ $3$ の $ab$-パスが $2^{-12}\epsilon^5N^2$ 本以上存在する.</span>

*<span class="segment" data-seg="BSG-p002-0026">Proof.</span>* <span class="segment" data-seg="BSG-p002-0027">まず $B$ の頂点のうち次数 $\epsilon N/2$ 未満のものを全て除去する.</span> <span class="segment" data-seg="BSG-p002-0028">このとき, $B$ には $\epsilon N/2$ 個以上の頂点が残る.</span> <span class="segment" data-seg="BSG-p002-0029">実際, $S=\{v\in B:\deg(v)\geq\epsilon N/2\}$ とすると</span>

$$
\epsilon N^2=|E|
=\sum_{v\in S}\deg(v)+\sum_{v\in B\setminus S}\deg(v)
\leq N\cdot|S|+\frac{\epsilon N}{2}\cdot N
$$

<span class="segment" data-seg="BSG-p002-0030">から $|S|\geq\epsilon N/2$ を得る.</span>

<span class="segment" data-seg="BSG-p002-0031">除去後のグラフを改めて $H=(A,B,E)$ と置き換えて証明する.</span> <span class="segment" data-seg="BSG-p002-0032">このとき $|E|\geq(\epsilon/2)N^2$ である.</span> <span class="segment" data-seg="BSG-p002-0033">実際, 次数高々 $\epsilon N/2$ の頂点を高々 $N$ 個除去しているので, 除去される辺数は $(\epsilon/2)N^2$ である.</span>

<span class="segment" data-seg="BSG-p002-0034">二つの頂点 $b,b'\in B$ が $|N(b)\cap N(b')|<(\epsilon^3/128)N$ を満たすとき, bad であると呼ぶ.</span> <span class="segment" data-seg="BSG-p002-0035">即ち, $(b,b')$ が bad であるとは $H$ において長さ $2$ の $bb'$-パスが少ないことを意味する.</span>

![Lemma 3.1 の二部グラフ](assets/figures/bsg-figure-1.png)

<span class="segment" data-seg="BSG-p003-0001">Figure 1: Lemma 3.1 の図示. 多くの長さ $3$ の $ab$ パスが存在するが, 途中で経由する頂点は必ずしも $A',B'$ に属するとは限らない.</span>

<span class="segment" data-seg="BSG-p003-0002">頂点 $v\in A$ に対してグラフ $G_v=(N(v),E_v)$ を, bad な頂点組 $b,b'\in N(v)$ に対して辺を引くことで得られるグラフとする.</span> <span class="segment" data-seg="BSG-p003-0003">つまり $E_v=\{\{b,b'\}\subseteq N(v):(b,b')\text{ is bad}\}$ である.</span> <span class="segment" data-seg="BSG-p003-0004">ランダムな $v\sim A$ に対する $G_v$ を考える.</span> <span class="segment" data-seg="BSG-p003-0005">頂点数の期待値は $\mathbb{E}[|N(v)|]=|E|/|A|\geq(\epsilon/2)N$ である.</span> <span class="segment" data-seg="BSG-p003-0006">固定した bad の組 $(b,b')$ に対し, $\Pr[b,b'\in N(v)]=\Pr[v\in N(b)\cap N(b')]=|N(b)\cap N(b')|/N\leq\epsilon^3/128$ であるので, $\mathbb{E}[|E_v|]=\sum_{\{b,b'\}:\,\mathrm{bad}}\Pr[\{b,b'\}\in E_v]\leq(\epsilon^3/256)N^2$ を得る.</span>

<span class="segment" data-seg="BSG-p003-0007">$B_v'\subseteq N(v)$ を, $G_v$ において次数が $(\epsilon^2/32)N$ 以下であるような頂点の集合とすると, Lemma 2.3 より $\mathbb{E}[|B_v'|]\geq\mathbb{E}[|N(v)|]-2\mathbb{E}[|E_v|]/((\epsilon^2/32)N)\geq(\epsilon/4)N$ を得る.</span> <span class="segment" data-seg="BSG-p003-0008">$\mathbb{E}_{v\sim A}[|B_v'|]\geq(\epsilon/4)N$ より, ある頂点 $v\in A$ が存在して $|B_v'|\geq(\epsilon/4)N$ となる.</span> <span class="segment" data-seg="BSG-p003-0009">$B'$ をこの時の $B_v'$ とする.</span> <span class="segment" data-seg="BSG-p003-0010">$A'=\{a\in A:|N(a)\cap B'|\geq(\epsilon^2/16)N\}$ とすると, $|A'|\geq(\epsilon^2/16)N$ である.</span>

<span class="segment" data-seg="BSG-p003-0011">実際, $a\sim A$ に対して確率変数 $|N(a)\cap B'|$ を考えると, $|E(A,B')|\geq(\epsilon/4)N\cdot(\epsilon/2)N=(\epsilon^2/8)N^2$ より $\mathbb{E}[|N(a)\cap B'|]=|E(A,B')|/N\geq(\epsilon^2/8)N$ である.</span> <span class="segment" data-seg="BSG-p003-0012">よって逆 Markov の不等式 (Lemma 2.2) から $|A'|/N=\Pr[|N(a)\cap B'|\geq(\epsilon^2/16)N]\geq\epsilon^2/16$ である.</span>

<span class="segment" data-seg="BSG-p003-0013">最後に $(A',B')$ が所望の性質を満たすことを言えば良い.</span> <span class="segment" data-seg="BSG-p003-0014">$a\in A',b\in B'$ を任意に固定し, 長さ $3$ の $ab$ パス $(a,b',a',b)$ の選び方を数える.</span> <span class="segment" data-seg="BSG-p003-0015">固定した $b\in B'$ の $G_v$ における次数の条件より bad な $(b,b')$ の取り方は高々 $(\epsilon^2/32)N$ 通りなので, これを $|N(a)\cap B'|$ から除くと, $(b,b')$ と bad にならないような $b'\in N(a)\cap B'$ は $(\epsilon^2/32)N$ 通りの選び方がある.</span> <span class="segment" data-seg="BSG-p003-0016">更に, $(b,b')$ は bad でないので長さ $2$ の $bb'$ パス $(b,a',b')$ が少なくとも $(\epsilon^3/128)N$ 通り存在する.</span> <span class="segment" data-seg="BSG-p003-0017">従って長さ $3$ の $ab$ パス $(a,b',a',b)$ は $(\epsilon^2/32)N\cdot(\epsilon^3/128)N=2^{-12}\epsilon^5N^2$ 通り存在する.</span>

*<span class="segment" data-seg="BSG-p003-0018">Proof of Theorem 1.1.</span>* <span class="segment" data-seg="BSG-p003-0019">$H=(A,B,E)$ を, $E=\{(a,b):a+b\in C\}$ で定まる二部グラフとする.</span> <span class="segment" data-seg="BSG-p003-0020">条件より $|E|\geq\epsilon N^2$ であり, Lemma 3.1 による頂点部分集合 $A'\subseteq A,B'\subseteq B$ を得る.</span> <span class="segment" data-seg="BSG-p003-0021">この二つの部分集合に対して $|A'+B'|\leq2^{12}c^3(1/\epsilon)^5N$ を示せばよい.</span>

<span class="segment" data-seg="BSG-p003-0022">$y=a+b\in A'+B'$ を一つとり, 任意の長さ $3$ のパス $(a,b',a',b)$ を考える.</span> <span class="segment" data-seg="BSG-p003-0023">$H$ の構成より $a+b',b'+a',a'+b\in C$ で, しかも $y=(a+b')-(a'+b')+(a'+b)$ と表せる.</span> <span class="segment" data-seg="BSG-p003-0024">このようなパスは $2^{-12}\epsilon^5N^2$ 本以上存在するため, 集合 $D_y:=\{(x,x',x'')\in C^3:y=x-x'+x''\}$ を考えると $|D_y|\geq2^{-12}\epsilon^5N^2$ である.</span> <span class="segment" data-seg="BSG-p003-0025">一方で任意の $y\in A'+B'$ に対し $D_y\subseteq C^3$ より $|D_y|\leq c^3N^3$ である.</span> <span class="segment" data-seg="BSG-p003-0026">さらに相異なる $y\neq y'$ に対し $D_y\cap D_{y'}=\varnothing$ より,</span>

$$
|A'+B'|\cdot2^{-12}\epsilon^5N^2
\leq\left|\bigcup_{y\in A'+B'}D_y\right|
\leq|C^3|
\leq c^3N^3
$$

<span class="segment" data-seg="BSG-p003-0027">を解いて $|A'+B'|\leq2^{12}c^3(1/\epsilon)^5N$ を得る.</span>

# <span class="segment" data-seg="BSG-p004-0001">References</span>

<span class="segment" data-seg="BSG-p004-0002">[BS94] Antal Balog and Endre Szemerédi. “A statistical theorem of set addition”. In: *Combinatorica* 14 (3 1994), pp. 263-268. URL: https://link.springer.com/article/10.1007/BF01212974.</span>

<span class="segment" data-seg="BSG-p004-0003">[Gow98] W. T. Gowers. “A New Proof of Szemerédi’s Theorem for Arithmetic Progressions of Length Four”. In: *Geometric And Functional Analysis* 8 (3 1998), pp. 529-551. URL: https://link.springer.com/article/10.1007/s000390050065.</span>

<span class="segment" data-seg="BSG-p004-0004">[Lov17] Shachar Lovett. “Additive Combinatorics and its Applications in Theoretical Computer Science”. In: *Theory of Computing* 1 (1 2017), pp. 1-55. URL: https://theoryofcomputing.org/articles/gs008/.</span>

<span class="segment" data-seg="BSG-p004-0005">[SSV05] B. Sudakov, E. Szemerédi, and V. H. Vu. “On a question of Erdős and Moser”. In: *Duke Mathematical Journal* 129 (1 2005).</span>
