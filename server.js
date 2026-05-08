const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3001;

app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept');
    next();
});

app.use(express.static(path.join(__dirname, 'public')));

app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.get('/api/questions', (req, res) => {
    const questions = require('./data/mbti-questions.json');
    res.json({
        success: true,
        total: questions.length,
        questions: questions
    });
});

app.post('/api/submit', express.json(), (req, res) => {
    const { answers } = req.body;
    const result = calculateMBTI(answers);
    res.json({
        success: true,
        result: result
    });
});

function calculateMBTI(answers) {
    let E = 0, I = 0, S = 0, N = 0, T = 0, F = 0, J = 0, P = 0;
    
    answers.forEach((answer, index) => {
        const scores = {
            A: [1, 0, 0.5, 1, 0.5, 1, 0, 0.5],
            B: [0, 1, 0, 0.5, 1, 0, 0.5, 0],
            C: [0, 0, 0, 0, 0, 0, 1, 1],
            D: [0.5, 0.5, 1, 0, 0, 0.5, 0.5, 0.5]
        };
        
        const score = scores[answer] || [0,0,0,0,0,0,0,0];
        E += score[0]; I += score[1];
        S += score[2]; N += score[3];
        T += score[4]; F += score[5];
        J += score[6]; P += score[7];
    });
    
    const type = (E >= I ? 'E' : 'I') + 
                 (S >= N ? 'S' : 'N') + 
                 (T >= F ? 'T' : 'F') + 
                 (J >= P ? 'J' : 'P');
    
    return { type, scores: { E, I, S, N, T, F, J, P } };
}

app.listen(PORT, '0.0.0.0', () => {
    console.log(`🔮 SBTI 性格测试 Mini App 运行中: http://localhost:${PORT}`);
    console.log(`🚀 已部署到 Render`);
});