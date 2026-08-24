# <span class="segment" data-seg="BSG-p001-0001">Balog-Szemerédi-Gowers Theorem</span>

<span class="segment" data-seg="BSG-p001-0002">Nobutaka Shimizu*</span>

<span class="segment" data-seg="BSG-p001-0003">April 29, 2022</span>

## <span class="segment" data-seg="BSG-p001-0004">Abstract</span>

<span class="segment" data-seg="BSG-p001-0005">Consider the sum obtained by choosing one element each from the abelian groups $A$ and $B$.</span> <span class="segment" data-seg="BSG-p001-0006">The Balog-Szemerédi-Gowers theorem captures the structural properties satisfied by $A$ and $B$ when most of these sums belong to some small set.</span> <span class="segment" data-seg="BSG-p001-0007">In this article, we introduce and prove this theorem.</span>

# <span class="segment" data-seg="BSG-p001-0008">1 Balog-Szemerédi-Gowers Theorem (BSG Theorem)</span>

<span class="segment" data-seg="BSG-p001-0009">For two subsets $A,B\subseteq G$ of an abelian group $G$, the size of $A+B:=\{a+b:a\in A,b\in B\}$ can in general be as large as $|A||B|$, but under what conditions will it be small?</span> <span class="segment" data-seg="BSG-p001-0010">Intuitively, if $A+B$ is small, one expects there to be many choices of $a\in A,b\in B$ satisfying $c=a+b$ for each $c\in A+B$.</span> <span class="segment" data-seg="BSG-p001-0011">That is, if the sum $a+b$ belongs to some small set $C\subseteq G$ for many pairs $(a,b)\in A\times B$, must $|A+B|$ be small?</span> <span class="segment" data-seg="BSG-p001-0012">Unfortunately, there is a counterexample.</span>

<span class="segment" data-seg="BSG-p001-0013">For example, let $V\subseteq\mathbb{F}_2^n$ be a subspace with $\dim V=d$, let $R\subseteq\mathbb{F}_2^n$ be a set of $2^d$ random vectors, and set $A=B=V\cup R$.</span> <span class="segment" data-seg="BSG-p001-0014">If $a\sim A,b\sim B$ are chosen at random, then with probability $1/4$ we have $a,b\in V$, and hence $a+b\in V$.</span> <span class="segment" data-seg="BSG-p001-0015">Thus, for $25\%$ of the pairs $(a,b)$, their sum belongs to $V$.</span> <span class="segment" data-seg="BSG-p001-0016">On the other hand, if $d$ is small, then with high probability $V\cup R$ spans a subspace of dimension $2d$, and $|A+B|=|\operatorname{span}(V\cup R)|=2^{2d}=|A||B|$.</span>

<span class="segment" data-seg="BSG-p001-0017">The BSG theorem asserts that, for $A$ and $B$ satisfying the same kind of condition, one can suitably choose dense subsets $A'\subseteq A,B'\subseteq B$ so that $|A'+B'|$ is small.</span> <span class="segment" data-seg="BSG-p001-0018">The BSG theorem was first proved by Balog and Szemerédi [BS94], and Gowers [Gow98] later gave a simpler proof.</span>

**<span class="segment" data-seg="BSG-p001-0019">Theorem 1.1 (BSG theorem [BS94; Gow98]).</span>** <span class="segment" data-seg="BSG-p001-0020">Let $G$ be an abelian group, and let $A,B\subseteq G$ satisfy $|A|=|B|=N$.</span> <span class="segment" data-seg="BSG-p001-0021">Suppose that there is a set $C\subseteq G$ of size $|C|=cN$ such that $\Pr_{a\sim A,b\sim B}[a+b\in C]\geq\epsilon$.</span> <span class="segment" data-seg="BSG-p001-0022">Then there exist $A'\subseteq A,B'\subseteq B$ satisfying $|A'|,|B'|\geq(\epsilon^2/16)N$ and $|A'+B'|\leq2^{12}c^3(1/\epsilon)^5N$.</span>

<span class="segment" data-seg="BSG-p001-0023">In this article, we present the proof due to Sudakov, Szemerédi, and Vu [SSV05].</span> <span class="segment" data-seg="BSG-p001-0024">The same proof is also presented in the survey by Lovett [Lov17], but the proof here fills in more of the intermediate steps by using, among other things, the reverse Markov inequality shown below.</span>

# <span class="segment" data-seg="BSG-p001-0025">2 Preliminaries</span>

<span class="segment" data-seg="BSG-p001-0026">When an element $x$ is chosen uniformly at random from a finite set $S$, we write $x\sim S$.</span>

<span class="segment" data-seg="BSG-p001-0027">For a finite set $V$ and $E\subseteq\binom{V}{2}$, we call $G=(V,E)$ a graph.</span> <span class="segment" data-seg="BSG-p001-0028">We call $V$ the vertex set and its elements vertices.</span> <span class="segment" data-seg="BSG-p001-0029">We call $E$ the edge set and its elements edges.</span> <span class="segment" data-seg="BSG-p001-0030">Two vertices $u,v\in V$ are said to be adjacent when $\{u,v\}\in E$.</span> <span class="segment" data-seg="BSG-p001-0031">We often abbreviate the edge $\{u,v\}$ as $uv$.</span> <span class="segment" data-seg="BSG-p001-0032">For a vertex $v$, we denote the set of vertices adjacent to $v$ by $N(v)$, call its cardinality the degree, and denote it by $\deg(v)$.</span> <span class="segment" data-seg="BSG-p001-0033">Thus, $N(v)=\{u\in V:uv\in E\}$ and $\deg(v)=|N(v)|$.</span>

<span class="segment" data-seg="BSG-p001-0034">* Tokyo Institute of Technology Email: shimizu.n.ah@m.titech.ac.jp</span>

<span class="segment" data-seg="BSG-p002-0001">A vertex sequence $(v_1,\ldots,v_k)$ satisfying $v_iv_{i+1}\in E$ for every $i\in\{1,\ldots,k-1\}$ is called a walk (or route); when its initial vertex $v_1$ and terminal vertex $v_k$ are specified, it is called a $v_1v_k$-walk.</span> <span class="segment" data-seg="BSG-p002-0002">The length of a walk $(v_1,\ldots,v_k)$ is defined to be $k-1$.</span> <span class="segment" data-seg="BSG-p002-0003">In particular, when all of $v_1,\ldots,v_k$ are distinct, it is called a path.</span> <span class="segment" data-seg="BSG-p002-0004">A walk satisfying $v_1=v_k$ is called a closed walk, and a closed walk in which $v_1,\ldots,v_{k-1}$ are distinct is called a circuit (or cycle).</span> <span class="segment" data-seg="BSG-p002-0005">A triple $(A,B,E)$ consisting of two finite sets $A,B$ and $E\subseteq A\times B$ is called a bipartite graph.</span> <span class="segment" data-seg="BSG-p002-0006">By identifying a bipartite graph with the graph $(A\cup B,E)$, we define $N(v)$, walks, and so forth.</span>

**<span class="segment" data-seg="BSG-p002-0007">Lemma 2.1 (Markov's inequality).</span>** <span class="segment" data-seg="BSG-p002-0008">If a nonnegative random variable $X$ satisfies $\mathbb{E}[X]<\infty$, then $\Pr[X\geq a]\leq\mathbb{E}[X]/a$ for every $a>0$.</span>

**<span class="segment" data-seg="BSG-p002-0009">Lemma 2.2 (reverse Markov inequality).</span>** <span class="segment" data-seg="BSG-p002-0010">Let $X$ be a random variable taking values in $[0,1]$, and let $\mu:=\mathbb{E}[X]\in(0,1)$.</span> <span class="segment" data-seg="BSG-p002-0011">Then $\Pr[X\geq\mu/2]\geq\mu/2$.</span>

*<span class="segment" data-seg="BSG-p002-0012">Proof.</span>* <span class="segment" data-seg="BSG-p002-0013">By Markov's inequality, for every $c\in(0,1)$,</span>

$$
\begin{aligned}
\Pr[X\leq c]
  &=\Pr[1-X\geq1-c]\\
  &\leq\frac{1-\mu}{1-c}\\
  &=1-\frac{\mu-c}{1-c}\\
  &\leq1-(\mu-c).
\end{aligned}
$$

<span class="segment" data-seg="BSG-p002-0014">It suffices to substitute $c=\mu/2$.</span>

**<span class="segment" data-seg="BSG-p002-0015">Lemma 2.3.</span>** <span class="segment" data-seg="BSG-p002-0016">For a graph $G=(V,E)$ and a parameter $c$, let $H=\{v\in V:\deg(v)\geq c\}$ and $L=V\setminus H$.</span> <span class="segment" data-seg="BSG-p002-0017">Then $|H|\leq2|E|/c$ and $|L|=|V|-|H|\geq|V|-2|E|/c$.</span>

*<span class="segment" data-seg="BSG-p002-0018">Proof.</span>* <span class="segment" data-seg="BSG-p002-0019">For a random vertex $v\sim V$, we have $\mathbb{E}[\deg(v)]=2|E|/|V|$.</span> <span class="segment" data-seg="BSG-p002-0020">Markov's inequality (Lemma 2.1) gives $|H|/|V|=\Pr[\deg(v)\geq c]\leq2|E|/(c|V|)$.</span>

# <span class="segment" data-seg="BSG-p002-0021">3 Proof</span>

<span class="segment" data-seg="BSG-p002-0022">We first prove the following graph-theoretic lemma.</span>

**<span class="segment" data-seg="BSG-p002-0023">Lemma 3.1 ([SSV05]).</span>** <span class="segment" data-seg="BSG-p002-0024">Let $H=(A,B,E)$ be a bipartite graph with $|A|=|B|=N$ and edge set $E\subseteq A\times B$ satisfying $|E|=\epsilon N^2$.</span> <span class="segment" data-seg="BSG-p002-0025">Then there exist $A'\subseteq A,B'\subseteq B$ satisfying $|A'|,|B'|\geq(\epsilon^2/16)N$ such that, for every $a\in A',b\in B'$, there are at least $2^{-12}\epsilon^5N^2$ $ab$-paths of length $3$.</span>

*<span class="segment" data-seg="BSG-p002-0026">Proof.</span>* <span class="segment" data-seg="BSG-p002-0027">First remove every vertex of $B$ having degree less than $\epsilon N/2$.</span> <span class="segment" data-seg="BSG-p002-0028">At least $\epsilon N/2$ vertices then remain in $B$.</span> <span class="segment" data-seg="BSG-p002-0029">Indeed, if $S=\{v\in B:\deg(v)\geq\epsilon N/2\}$, then</span>

$$
\epsilon N^2=|E|
=\sum_{v\in S}\deg(v)+\sum_{v\in B\setminus S}\deg(v)
\leq N\cdot|S|+\frac{\epsilon N}{2}\cdot N
$$

<span class="segment" data-seg="BSG-p002-0030">gives $|S|\geq\epsilon N/2$.</span>

<span class="segment" data-seg="BSG-p002-0031">For the rest of the proof, relabel the graph after removal as $H=(A,B,E)$.</span> <span class="segment" data-seg="BSG-p002-0032">We then have $|E|\geq(\epsilon/2)N^2$.</span> <span class="segment" data-seg="BSG-p002-0033">Indeed, at most $N$ vertices, each having degree at most $\epsilon N/2$, were removed, so at most $(\epsilon/2)N^2$ edges were removed.</span>

<span class="segment" data-seg="BSG-p002-0034">Call two vertices $b,b'\in B$ bad when $|N(b)\cap N(b')|<(\epsilon^3/128)N$.</span> <span class="segment" data-seg="BSG-p002-0035">Thus, $(b,b')$ being bad means that there are few $bb'$-paths of length $2$ in $H$.</span>

![The bipartite graph in Lemma 3.1](assets/figures/bsg-figure-1.png)

<span class="segment" data-seg="BSG-p003-0001">Figure 1: Illustration of Lemma 3.1. There are many $ab$-paths of length $3$, but the intermediate vertices need not belong to $A'$ and $B'$.</span>

<span class="segment" data-seg="BSG-p003-0002">For a vertex $v\in A$, define the graph $G_v=(N(v),E_v)$ by drawing an edge for every bad pair of vertices $b,b'\in N(v)$.</span> <span class="segment" data-seg="BSG-p003-0003">In other words, $E_v=\{\{b,b'\}\subseteq N(v):(b,b')\text{ is bad}\}$.</span> <span class="segment" data-seg="BSG-p003-0004">Consider $G_v$ for a random $v\sim A$.</span> <span class="segment" data-seg="BSG-p003-0005">The expected number of vertices is $\mathbb{E}[|N(v)|]=|E|/|A|\geq(\epsilon/2)N$.</span> <span class="segment" data-seg="BSG-p003-0006">For a fixed bad pair $(b,b')$, we have $\Pr[b,b'\in N(v)]=\Pr[v\in N(b)\cap N(b')]=|N(b)\cap N(b')|/N\leq\epsilon^3/128$, and therefore $\mathbb{E}[|E_v|]=\sum_{\{b,b'\}:\,\mathrm{bad}}\Pr[\{b,b'\}\in E_v]\leq(\epsilon^3/256)N^2$.</span>

<span class="segment" data-seg="BSG-p003-0007">Let $B_v'\subseteq N(v)$ be the set of vertices whose degree in $G_v$ is at most $(\epsilon^2/32)N$; Lemma 2.3 then gives $\mathbb{E}[|B_v'|]\geq\mathbb{E}[|N(v)|]-2\mathbb{E}[|E_v|]/((\epsilon^2/32)N)\geq(\epsilon/4)N$.</span> <span class="segment" data-seg="BSG-p003-0008">Since $\mathbb{E}_{v\sim A}[|B_v'|]\geq(\epsilon/4)N$, there is a vertex $v\in A$ such that $|B_v'|\geq(\epsilon/4)N$.</span> <span class="segment" data-seg="BSG-p003-0009">Let $B'$ be this $B_v'$.</span> <span class="segment" data-seg="BSG-p003-0010">If $A'=\{a\in A:|N(a)\cap B'|\geq(\epsilon^2/16)N\}$, then $|A'|\geq(\epsilon^2/16)N$.</span>

<span class="segment" data-seg="BSG-p003-0011">Indeed, for a random $a\sim A$, consider the random variable $|N(a)\cap B'|$; since $|E(A,B')|\geq(\epsilon/4)N\cdot(\epsilon/2)N=(\epsilon^2/8)N^2$, we have $\mathbb{E}[|N(a)\cap B'|]=|E(A,B')|/N\geq(\epsilon^2/8)N$.</span> <span class="segment" data-seg="BSG-p003-0012">The reverse Markov inequality (Lemma 2.2) therefore gives $|A'|/N=\Pr[|N(a)\cap B'|\geq(\epsilon^2/16)N]\geq\epsilon^2/16$.</span>

<span class="segment" data-seg="BSG-p003-0013">It remains to show that $(A',B')$ has the desired property.</span> <span class="segment" data-seg="BSG-p003-0014">Fix arbitrary $a\in A',b\in B'$ and count the choices of an $ab$-path $(a,b',a',b)$ of length $3$.</span> <span class="segment" data-seg="BSG-p003-0015">By the degree condition for the fixed $b\in B'$ in $G_v$, there are at most $(\epsilon^2/32)N$ choices of $b'$ for which $(b,b')$ is bad; removing these from $|N(a)\cap B'|$ leaves $(\epsilon^2/32)N$ choices of $b'\in N(a)\cap B'$ for which $(b,b')$ is not bad.</span> <span class="segment" data-seg="BSG-p003-0016">Furthermore, because $(b,b')$ is not bad, there are at least $(\epsilon^3/128)N$ $bb'$-paths $(b,a',b')$ of length $2$.</span> <span class="segment" data-seg="BSG-p003-0017">Consequently, there are $(\epsilon^2/32)N\cdot(\epsilon^3/128)N=2^{-12}\epsilon^5N^2$ $ab$-paths $(a,b',a',b)$ of length $3$.</span>

*<span class="segment" data-seg="BSG-p003-0018">Proof of Theorem 1.1.</span>* <span class="segment" data-seg="BSG-p003-0019">Let $H=(A,B,E)$ be the bipartite graph defined by $E=\{(a,b):a+b\in C\}$.</span> <span class="segment" data-seg="BSG-p003-0020">The hypothesis gives $|E|\geq\epsilon N^2$, and Lemma 3.1 gives vertex subsets $A'\subseteq A,B'\subseteq B$.</span> <span class="segment" data-seg="BSG-p003-0021">It suffices to show that $|A'+B'|\leq2^{12}c^3(1/\epsilon)^5N$ for these two subsets.</span>

<span class="segment" data-seg="BSG-p003-0022">Choose $y=a+b\in A'+B'$ and consider any path $(a,b',a',b)$ of length $3$.</span> <span class="segment" data-seg="BSG-p003-0023">By the construction of $H$, we have $a+b',b'+a',a'+b\in C$, and moreover $y=(a+b')-(a'+b')+(a'+b)$.</span> <span class="segment" data-seg="BSG-p003-0024">There are at least $2^{-12}\epsilon^5N^2$ such paths, so if we consider the set $D_y:=\{(x,x',x'')\in C^3:y=x-x'+x''\}$, then $|D_y|\geq2^{-12}\epsilon^5N^2$.</span> <span class="segment" data-seg="BSG-p003-0025">On the other hand, for every $y\in A'+B'$, the inclusion $D_y\subseteq C^3$ gives $|D_y|\leq c^3N^3$.</span> <span class="segment" data-seg="BSG-p003-0026">Furthermore, $D_y\cap D_{y'}=\varnothing$ for distinct $y\neq y'$, and hence</span>

$$
|A'+B'|\cdot2^{-12}\epsilon^5N^2
\leq\left|\bigcup_{y\in A'+B'}D_y\right|
\leq|C^3|
\leq c^3N^3
$$

<span class="segment" data-seg="BSG-p003-0027">Solving this inequality gives $|A'+B'|\leq2^{12}c^3(1/\epsilon)^5N$.</span>

# <span class="segment" data-seg="BSG-p004-0001">References</span>

<span class="segment" data-seg="BSG-p004-0002">[BS94] Antal Balog and Endre Szemerédi. “A statistical theorem of set addition”. In: *Combinatorica* 14 (3 1994), pp. 263-268. URL: https://link.springer.com/article/10.1007/BF01212974.</span>

<span class="segment" data-seg="BSG-p004-0003">[Gow98] W. T. Gowers. “A New Proof of Szemerédi’s Theorem for Arithmetic Progressions of Length Four”. In: *Geometric And Functional Analysis* 8 (3 1998), pp. 529-551. URL: https://link.springer.com/article/10.1007/s000390050065.</span>

<span class="segment" data-seg="BSG-p004-0004">[Lov17] Shachar Lovett. “Additive Combinatorics and its Applications in Theoretical Computer Science”. In: *Theory of Computing* 1 (1 2017), pp. 1-55. URL: https://theoryofcomputing.org/articles/gs008/.</span>

<span class="segment" data-seg="BSG-p004-0005">[SSV05] B. Sudakov, E. Szemerédi, and V. H. Vu. “On a question of Erdős and Moser”. In: *Duke Mathematical Journal* 129 (1 2005).</span>
